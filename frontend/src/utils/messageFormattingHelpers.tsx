import React from 'react';

/** Strip common inline markdown; keep visible text only. */
export function stripInlineMarkdown(s: string): string {
  let t = s;
  t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  t = t.replace(/\*\*(.+?)\*\*/g, '$1');
  t = t.replace(/__(.+?)__/g, '$1');
  t = t.replace(/`([^`]+)`/g, '$1');
  t = t.replace(/\*(.+?)\*/g, '$1');
  t = t.replace(/_(.+?)_/g, '$1');
  return t;
}

/** Remove markdown markers and normalize list lines to leading "• " for display. */
export function normalizeAssistantText(raw: string): string {
  const lines = raw.split(/\r?\n/);
  const out: string[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === '') {
      out.push('');
      continue;
    }
    if (/^-{3,}$/.test(trimmed)) {
      out.push('');
      continue;
    }
    const heading = trimmed.match(/^#{1,6}\s+(.+)$/);
    if (heading) {
      out.push(stripInlineMarkdown(heading[1]));
      continue;
    }
    const bullet = trimmed.match(/^[-*+]\s+(.+)$/);
    if (bullet) {
      out.push('• ' + stripInlineMarkdown(bullet[1]));
      continue;
    }
    const ordered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      out.push('• ' + stripInlineMarkdown(ordered[1]));
      continue;
    }
    out.push(stripInlineMarkdown(trimmed));
  }
  return out.join('\n');
}

/** Drop blank lines between consecutive bullet rows so lists stay visually tight. */
export function collapseBlankLinesBetweenBullets(lines: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === '') {
      const prev = out[out.length - 1];
      const nextNonEmpty = lines.slice(i + 1).find((l) => l.trim() !== '');
      if (prev?.trimStart().startsWith('• ') && nextNonEmpty?.trimStart().startsWith('• ')) {
        continue;
      }
    }
    out.push(line);
  }
  return out;
}

export function renderAssistantMessage(text: string): React.ReactNode {
  if (!text) {
    return null;
  }
  const lines = collapseBlankLinesBetweenBullets(text.split('\n'));
  return (
    <div className="flex flex-col gap-1">
      {lines.map((line, idx) => {
        if (line.trim() === '') {
          return <div key={idx} className="h-1 shrink-0" aria-hidden />;
        }
        if (line.startsWith('• ')) {
          return (
            <div key={idx} className="flex gap-2 items-start py-0 leading-snug">
              <span className="shrink-0 text-slate-600 select-none pt-0.5" aria-hidden>
                •
              </span>
              <span className="flex-1 min-w-0">{line.slice(2)}</span>
            </div>
          );
        }
        return (
          <p key={idx} className="leading-relaxed m-0 first:mt-0">
            {line}
          </p>
        );
      })}
    </div>
  );
}
