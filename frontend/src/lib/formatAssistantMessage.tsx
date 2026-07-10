import type { ReactNode } from "react";

export type ListItemContent = {
  main: string;
  subItems?: string[];
};

type ContentBlock =
  | { type: "paragraph"; text: string }
  | { type: "section-list"; items: ListItemContent[] }
  | { type: "ordered-list"; items: string[] }
  | { type: "unordered-list"; items: string[] };

function parseBoldHeadingLine(line: string): { title: string; rest: string } | null {
  const m = line.match(/^\*\*([^*]+)\*\*:?\s*(.*)$/);
  if (!m) return null;
  return { title: m[1].trim(), rest: m[2].trim() };
}

function stripLeadingNumber(line: string): string {
  return line.replace(/^\d+[.)]\s+/, "").trim();
}

function collectSubItems(lines: string[], startIndex: number): { subItems: string[]; nextIndex: number } {
  const subItems: string[] = [];
  let i = startIndex;

  while (i < lines.length) {
    const l = lines[i].trim();
    if (!l) {
      i += 1;
      continue;
    }
    if (parseBoldHeadingLine(l) || /^\d+[.)]\s/.test(l)) break;

    const bullet = l.match(/^[-•*]\s+(.+)$/);
    subItems.push(bullet ? bullet[1] : l);
    i += 1;
  }

  return { subItems, nextIndex: i };
}

function buildSectionMain(parsed: { title: string; rest: string }): string {
  return parsed.rest
    ? `**${parsed.title}:** ${parsed.rest}`
    : `**${parsed.title}:**`;
}

function collectSectionBlock(
  lines: string[],
  startIndex: number,
  firstLine: string
): { block: ContentBlock; nextIndex: number } | null {
  const items: ListItemContent[] = [];
  let i = startIndex;

  const firstBold = parseBoldHeadingLine(stripLeadingNumber(firstLine));
  const firstPlain = firstBold
    ? null
    : stripLeadingNumber(firstLine).match(/^\*\*([^*]+)\*\*:?\s*(.*)$/);

  if (firstBold) {
    items.push({ main: buildSectionMain(firstBold) });
    i += 1;
  } else if (firstPlain) {
    const parsed = parseBoldHeadingLine(stripLeadingNumber(firstLine));
    if (parsed) {
      items.push({ main: buildSectionMain(parsed) });
      i += 1;
    }
  } else {
    return null;
  }

  const firstSubs = collectSubItems(lines, i);
  if (firstSubs.subItems.length) {
    items[0].subItems = firstSubs.subItems;
  }
  i = firstSubs.nextIndex;

  while (i < lines.length) {
    const l = lines[i].trim();
    if (!l) {
      i += 1;
      continue;
    }

    let parsed = parseBoldHeadingLine(stripLeadingNumber(l));
    if (!parsed && /^\d+[.)]\s/.test(l)) {
      parsed = parseBoldHeadingLine(stripLeadingNumber(l));
    }
    if (!parsed) break;

    items.push({ main: buildSectionMain(parsed) });
    i += 1;
    const subs = collectSubItems(lines, i);
    if (subs.subItems.length) {
      items[items.length - 1].subItems = subs.subItems;
    }
    i = subs.nextIndex;
  }

  if (!items.length) return null;
  return { block: { type: "section-list", items }, nextIndex: i };
}

function splitEmbeddedBoldSections(text: string): ContentBlock | ContentBlock[] {
  const parts = text
    .split(/(?=\*\*[^*]+\*\*:?)/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (parts.length >= 2 && parts.every((p) => /^\*\*[^*]+\*\*/.test(p))) {
    return {
      type: "section-list",
      items: parts.map((p) => ({ main: p })),
    };
  }
  return { type: "paragraph", text };
}

export function parseAssistantContent(text: string): ContentBlock[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ContentBlock[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) {
      i += 1;
      continue;
    }

    const isSectionStart =
      parseBoldHeadingLine(stripLeadingNumber(line)) != null ||
      (/^\d+[.)]\s/.test(line) && /\*\*/.test(line));

    if (isSectionStart) {
      const collected = collectSectionBlock(lines, i, line);
      if (collected && collected.block.type === "section-list") {
        blocks.push(collected.block);
        i = collected.nextIndex;
        continue;
      }
    }

    const bullet = line.match(/^[-•*]\s+(.+)$/);
    if (bullet) {
      const items: string[] = [];
      while (i < lines.length) {
        const m = lines[i].trim().match(/^[-•*]\s+(.+)$/);
        if (!m) break;
        items.push(m[1]);
        i += 1;
      }
      blocks.push({ type: "unordered-list", items });
      continue;
    }

    const paraLines: string[] = [];
    while (i < lines.length) {
      const l = lines[i].trim();
      if (!l) break;
      const nextIsSection =
        parseBoldHeadingLine(stripLeadingNumber(l)) != null ||
        (/^\d+[.)]\s/.test(l) && /\*\*/.test(l));
      if (nextIsSection || /^[-•*]\s/.test(l)) break;
      paraLines.push(l);
      i += 1;
    }

    if (paraLines.length) {
      const joined = paraLines.join(" ");
      const embedded = splitEmbeddedBoldSections(joined);
      if (Array.isArray(embedded)) {
        blocks.push(...embedded);
      } else if (embedded.type === "section-list") {
        blocks.push(embedded);
      } else {
        blocks.push({ type: "paragraph", text: joined });
      }
    }
  }

  if (!blocks.length && text.trim()) {
    const embedded = splitEmbeddedBoldSections(text.trim());
    if (Array.isArray(embedded)) {
      blocks.push(...embedded);
    } else {
      blocks.push(embedded);
    }
  }

  return blocks;
}

export function renderInlineMarkdown(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-ink">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <span key={idx}>{part}</span>;
  });
}

function NumberedSubList({ items }: { items: string[] }) {
  return (
    <ol className="mt-2 space-y-1.5">
      {items.map((sub, k) => (
        <li key={k} className="flex gap-2.5 text-sm">
          <span className="w-5 shrink-0 text-right font-semibold tabular-nums text-ink-muted">
            {k + 1}.
          </span>
          <span className="min-w-0 flex-1">{renderInlineMarkdown(sub)}</span>
        </li>
      ))}
    </ol>
  );
}

function SectionListBlock({ items }: { items: ListItemContent[] }) {
  return (
    <div className="space-y-3">
      {items.map((item, j) => (
        <div key={j}>
          <div>{renderInlineMarkdown(item.main)}</div>
          {item.subItems && item.subItems.length > 0 && (
            <NumberedSubList items={item.subItems} />
          )}
        </div>
      ))}
    </div>
  );
}

export function FormattedAssistantText({ content }: { content: string }) {
  const blocks = parseAssistantContent(content);

  return (
    <div className="space-y-3 text-sm leading-relaxed text-ink">
      {blocks.map((block, i) => {
        if (block.type === "paragraph") {
          return (
            <p key={i} className="text-justify">
              {renderInlineMarkdown(block.text)}
            </p>
          );
        }
        if (block.type === "section-list") {
          return <SectionListBlock key={i} items={block.items} />;
        }
        if (block.type === "ordered-list") {
          return <NumberedSubList key={i} items={block.items} />;
        }
        return (
          <ul key={i} className="list-disc space-y-1.5 pl-5">
            {block.items.map((item, j) => (
              <li key={j}>{renderInlineMarkdown(item)}</li>
            ))}
          </ul>
        );
      })}
    </div>
  );
}
