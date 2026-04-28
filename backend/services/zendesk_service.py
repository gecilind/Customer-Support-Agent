from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from config import Settings


@dataclass(frozen=True)
class ZendeskArticle:
    article_id: int
    title: str
    body_text: str
    html_url: str
    section_name: str
    category_name: str
    updated_at: str


class ZendeskService:
    """Fetches Help Center categories, sections, and articles (public read API)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def locale(self) -> str:
        return self._settings.zendesk_locale

    def source_url_prefix_for_deletion(self) -> str:
        """Prefix for DELETE ... WHERE source LIKE prefix||'%' (Zendesk article URLs)."""
        return f"{self._settings.zendesk_help_center_url.rstrip('/')}/"

    def _hc_url(self, path: str) -> str:
        base = self._settings.zendesk_help_center_url.rstrip("/")
        loc = self._settings.zendesk_locale.strip().strip("/") or "de"
        path = path.lstrip("/")
        return f"{base}/api/v2/help_center/{loc}/{path}"

    @staticmethod
    def _strip_html_to_text(html: str | None) -> str:
        if not html or not str(html).strip():
            return ""
        soup = BeautifulSoup(str(html), "html.parser")
        text = soup.get_text(separator="\n")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    async def _get_json(self, client: httpx.AsyncClient, url: str) -> dict:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object from {url!r}")
        return data

    async def _fetch_categories(self, client: httpx.AsyncClient) -> list[dict]:
        url = self._hc_url("categories.json")
        out: list[dict] = []
        while url:
            try:
                data = await self._get_json(client, url)
            except httpx.HTTPError as exc:
                print(f"[INGEST] Zendesk categories fetch failed: {exc}")
                raise
            batch = data.get("categories") or []
            out.extend(batch)
            url = data.get("next_page")
        return out

    async def _fetch_sections(self, client: httpx.AsyncClient) -> list[dict]:
        url = self._hc_url("sections.json")
        out: list[dict] = []
        while url:
            try:
                data = await self._get_json(client, url)
            except httpx.HTTPError as exc:
                print(f"[INGEST] Zendesk sections fetch failed: {exc}")
                raise
            batch = data.get("sections") or []
            out.extend(batch)
            url = data.get("next_page")
        return out

    async def _fetch_article_detail_raw_body(self, client: httpx.AsyncClient, article_id: int) -> str:
        url = self._hc_url(f"articles/{article_id}.json")
        data = await self._get_json(client, url)
        article = data.get("article") or {}
        raw = article.get("body")
        if raw is None:
            return ""
        return str(raw)

    async def _hydrate_missing_bodies(
        self, client: httpx.AsyncClient, raw_articles: list[dict]
    ) -> None:
        """List responses often omit `body`; fill with Show Article when needed."""
        missing_ids = [
            int(a["id"])
            for a in raw_articles
            if a.get("id") is not None and not (a.get("body") and str(a.get("body")).strip())
        ]
        if not missing_ids:
            return
        print(f"[INGEST] Zendesk: fetching full body for {len(missing_ids)} articles (list omits body)")
        sem = asyncio.Semaphore(8)

        async def one(aid: int) -> tuple[int, str]:
            async with sem:
                try:
                    body = await self._fetch_article_detail_raw_body(client, aid)
                    return aid, body
                except httpx.HTTPError as exc:
                    print(f"[INGEST] Zendesk: article {aid} body fetch failed: {exc}")
                    return aid, ""

        results = await asyncio.gather(*[one(aid) for aid in missing_ids])
        by_id = dict(results)
        for a in raw_articles:
            aid = a.get("id")
            if aid is None:
                continue
            if not (a.get("body") and str(a.get("body")).strip()):
                a["body"] = by_id.get(int(aid), "")

    async def fetch_all_articles(self) -> list[ZendeskArticle]:
        base = self._settings.zendesk_help_center_url.rstrip("/")
        per_page = self._settings.zendesk_articles_per_page
        loc = self._settings.zendesk_locale

        print(f"[INGEST] Zendesk: connecting to {base} (locale={loc})")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                categories_raw = await self._fetch_categories(client)
            except httpx.HTTPError:
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"[INGEST] Zendesk categories fetch failed: {exc}")
                raise

            try:
                sections_raw = await self._fetch_sections(client)
            except httpx.HTTPError:
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"[INGEST] Zendesk sections fetch failed: {exc}")
                raise

            category_by_id: dict[int, str] = {}
            for c in categories_raw:
                cid = c.get("id")
                name = c.get("name")
                if cid is not None and name:
                    category_by_id[int(cid)] = str(name)

            section_by_id: dict[int, tuple[str, int]] = {}
            for s in sections_raw:
                sid = s.get("id")
                sname = s.get("name")
                cat_id = s.get("category_id")
                if sid is None or not sname or cat_id is None:
                    continue
                section_by_id[int(sid)] = (str(sname), int(cat_id))

            print(
                f"[INGEST] Zendesk: loaded {len(category_by_id)} categories, "
                f"{len(section_by_id)} sections"
            )

            raw_articles: list[dict] = []
            page = 1
            next_url: str | None = self._hc_url(
                f"articles.json?page={page}&per_page={per_page}"
            )

            while next_url:
                try:
                    data = await self._get_json(client, next_url)
                except httpx.HTTPError as exc:
                    print(f"[INGEST] Zendesk articles page fetch failed ({next_url}): {exc}")
                    print("[INGEST] Zendesk: stopping pagination; returning articles collected so far")
                    break
                batch = data.get("articles") or []
                raw_articles.extend(batch)
                print(f"[INGEST] Zendesk: articles page {page}, +{len(batch)} (total {len(raw_articles)})")
                next_url = data.get("next_page")
                page += 1

            await self._hydrate_missing_bodies(client, raw_articles)

            out: list[ZendeskArticle] = []
            for a in raw_articles:
                section_id = a.get("section_id")
                if section_id is None:
                    continue
                sid = int(section_id)
                if sid not in section_by_id:
                    continue
                section_name, category_id = section_by_id[sid]
                category_name = category_by_id.get(category_id)
                if not category_name:
                    continue
                aid = a.get("id")
                if aid is None:
                    continue
                title = (a.get("title") or "").strip()
                html_url = (a.get("html_url") or "").strip()
                if not html_url:
                    continue
                body_raw = a.get("body")
                body_text = self._strip_html_to_text(body_raw) if body_raw else ""
                updated_at = str(a.get("updated_at") or "")

                out.append(
                    ZendeskArticle(
                        article_id=int(aid),
                        title=title,
                        body_text=body_text,
                        html_url=html_url,
                        section_name=section_name,
                        category_name=category_name,
                        updated_at=updated_at,
                    )
                )

            return out
