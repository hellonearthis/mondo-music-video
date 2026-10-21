// Pure Functional Markdown Renderer for Mondo Studio In-App Guides and Documentation.

export const escapeHtml = (str = "") =>
  str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

export const slugify = (text = "") =>
  text
    .toLowerCase()
    .replace(/<[^>]*>/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

export const parseInline = (text = "") => {
  if (!text) return "";

  // 1. Protect inline code spans with indexed placeholders
  const codeBlocks = [];
  let protectedText = text.replace(/`([^`]+)`/g, (_, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(`<code>${escapeHtml(code)}</code>`);
    return `\x00CODE_${idx}\x00`;
  });

  // 2. Escape any raw HTML characters in non-code text
  protectedText = escapeHtml(protectedText);

  // 3. Bold + Italic, Bold, Italic, Strikethrough (processed before links to prevent attribute mangling)
  protectedText = protectedText
    .replace(/\*\*\*([^*]+)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/___([^_]+)___/g, "<strong><em>$1</em></strong>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/(^|[^\w])_([^_]+)_(?=[^\w]|$)/g, "$1<em>$2</em>")
    .replace(/~~([^~]+)~~/g, "<del>$1</del>");

  // 4. Links [label](url): only http(s) opens in a new tab, #anchors stay in the page, anything else is plain text
  protectedText = protectedText.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    (_, label, url) => {
      const href = url.trim();
      if (/^https?:\/\//i.test(href)) return `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      if (/^#[\w-]*$/.test(href)) return `<a href="#md-${href.slice(1)}">${label}</a>`;
      return label;
    }
  );

  // 5. Restore inline code spans
  return protectedText.replace(/\x00CODE_(\d+)\x00/g, (_, idx) => codeBlocks[Number(idx)]);
};

const parseTableAlignments = (delimiterLine = "") =>
  delimiterLine
    .split("|")
    .slice(1, -1)
    .map((cell) => {
      const trimmed = cell.trim();
      const left = trimmed.startsWith(":");
      const right = trimmed.endsWith(":");
      if (left && right) return "center";
      if (right) return "right";
      return "left";
    });

const parseTableRow = (line = "") =>
  line
    .split("|")
    .slice(1, -1)
    .map((cell) => cell.trim());

export const renderMarkdown = (markdown = "") => {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const htmlParts = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    // Blank line
    if (!line.trim()) {
      index++;
      continue;
    }

    // Fenced Code Block
    if (line.trim().startsWith("```")) {
      const match = line.trim().match(/^```(\w*)/);
      const lang = match ? match[1].toLowerCase() : "";
      const codeLines = [];
      index++;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index++;
      }
      index++; // skip closing fence
      const rawCode = codeLines.join("\n");
      const safeCode = escapeHtml(rawCode);
      const displayLang = lang || "text";
      htmlParts.push(
        `<div class="md-code-block" data-lang="${displayLang}">` +
          `<div class="md-code-header">` +
            `<span class="md-code-lang">${displayLang}</span>` +
            `<button type="button" class="md-copy-btn" data-tooltip="Copy code snippet">Copy</button>` +
          `</div>` +
          `<pre><code class="language-${displayLang}">${safeCode}</code></pre>` +
        `</div>`
      );
      continue;
    }

    // Heading (# to ######)
    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const titleText = headingMatch[2].trim();
      const id = `md-${slugify(titleText)}`;
      const parsedTitle = parseInline(titleText);
      htmlParts.push(`<h${level} id="${id}">${parsedTitle}</h${level}>`);
      index++;
      continue;
    }

    // Horizontal Rule (---, ***, ___)
    if (/^(\*{3,}|-{3,}|_{3,})$/.test(line.trim())) {
      htmlParts.push(`<hr class="md-hr" />`);
      index++;
      continue;
    }

    // Blockquote (> ...)
    if (line.trim().startsWith(">")) {
      const quoteLines = [];
      while (
        index < lines.length &&
        (lines[index].trim().startsWith(">") ||
          (lines[index].trim() &&
            quoteLines.length > 0 &&
            !lines[index].match(/^(#{1,6}\s|```|\||[-*+]\s|\d+\.\s)/)))
      ) {
        quoteLines.push(lines[index].replace(/^\s*>\s?/, ""));
        index++;
      }
      const quoteHtml = renderMarkdown(quoteLines.join("\n"));
      htmlParts.push(`<blockquote class="md-blockquote">${quoteHtml}</blockquote>`);
      continue;
    }

    // GFM Table
    if (line.includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-+:?\s*\|/.test(lines[index + 1])) {
      const headerRow = parseTableRow(line);
      const alignments = parseTableAlignments(lines[index + 1]);
      index += 2;

      const bodyRows = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        bodyRows.push(parseTableRow(lines[index]));
        index++;
      }

      const thead =
        `<thead><tr>` +
        headerRow
          .map((th, colIdx) => {
            const align = alignments[colIdx] ? ` style="text-align:${alignments[colIdx]}"` : "";
            return `<th${align}>${parseInline(th)}</th>`;
          })
          .join("") +
        `</tr></thead>`;

      const tbody =
        `<tbody>` +
        bodyRows
          .map(
            (row) =>
              `<tr>` +
              row
                .map((td, colIdx) => {
                  const align = alignments[colIdx] ? ` style="text-align:${alignments[colIdx]}"` : "";
                  return `<td${align}>${parseInline(td)}</td>`;
                })
                .join("") +
              `</tr>`
          )
          .join("") +
        `</tbody>`;

      htmlParts.push(`<div class="md-table-wrapper"><table class="md-table">${thead}${tbody}</table></div>`);
      continue;
    }

    // Unordered or Ordered List
    const listMatch = line.match(/^(\s*)([-*+]|\d+\.)\s+(.*)$/);
    if (listMatch) {
      const isOrdered = /^\d+\./.test(listMatch[2]);
      const listTag = isOrdered ? "ol" : "ul";
      const items = [];

      while (index < lines.length) {
        const itemMatch = lines[index].match(/^(\s*)([-*+]|\d+\.)\s+(.*)$/);
        if (itemMatch) {
          const itemTextLines = [itemMatch[3]];
          index++;
          while (
            index < lines.length &&
            lines[index].trim() &&
            (lines[index].startsWith("   ") ||
              lines[index].startsWith("\t") ||
              lines[index].match(/^\s+[-*+]/))
          ) {
            itemTextLines.push(lines[index].trim());
            index++;
          }
          items.push(itemTextLines.join("\n"));
        } else if (
          lines[index].trim() &&
          (lines[index].startsWith("   ") || lines[index].startsWith("\t"))
        ) {
          if (items.length > 0) {
            items[items.length - 1] += "\n" + lines[index].trim();
          }
          index++;
        } else {
          break;
        }
      }

      const listHtml =
        `<${listTag}>` +
        items
          .map((item) => {
            const linesInItem = item.split("\n");
            const firstLine = linesInItem[0];
            const rest = linesInItem.slice(1).join("\n");
            let renderedItem = parseInline(firstLine);
            if (rest.trim()) {
              renderedItem += " " + renderMarkdown(rest);
            }
            return `<li>${renderedItem}</li>`;
          })
          .join("") +
        `</${listTag}>`;

      htmlParts.push(listHtml);
      continue;
    }

    // Regular Paragraph
    const paraLines = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].trim().startsWith("```") &&
      !lines[index].match(/^#{1,6}\s/) &&
      !lines[index].trim().startsWith(">") &&
      !lines[index].match(/^(\*{3,}|-{3,}|_{3,})$/) &&
      !(lines[index].includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-+:?\s*\|/.test(lines[index + 1])) &&
      !lines[index].match(/^(\s*)([-*+]|\d+\.)\s+/)
    ) {
      paraLines.push(lines[index].trim());
      index++;
    }

    if (paraLines.length > 0) {
      htmlParts.push(`<p>${parseInline(paraLines.join(" "))}</p>`);
    }
  }

  return htmlParts.join("\n");
};
