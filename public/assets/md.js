// md(text) → HTML for the projects' own markdown files (plans, drafts, profiles): headings, lists,
// tables, block quotes, code, bold/italic/code/links. Everything is escaped first, quotes too because
// links put text in an attribute, so it is safe for text from files and job ads. Pair with the .md
// styles in page.css.
(function () {
  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  function inline(s) {
    const codes = [];
    s = esc(s).replace(/`([^`]+)`/g, (_, c) => `\u0000${codes.push(c) - 1}\u0000`);
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*\w])\*(?!\s)(.+?)\*(?!\w)/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[i]}</code>`).replace(/\u0001/g, "<br>");
  }
  function md(src) {
    const out = [], lines = String(src || "").replace(/\r/g, "").split("\n");
    let para = [], list = null, quote = [];
    const closePara = () => { if (para.length) { out.push(`<p>${inline(para.join(" ").replace(/ \u0001/g, "\u0001"))}</p>`); para = []; } };
    const closeList = () => {
      if (!list) return;
      out.push(`<${list.tag}>${list.items.map(it => `<li>${inline(it.text)}${it.sub.length ? `<ul>${it.sub.map(u => `<li>${inline(u)}</li>`).join("")}</ul>` : ""}</li>`).join("")}</${list.tag}>`);
      list = null;
    };
    const closeQuote = () => { if (quote.length) { out.push(`<blockquote>${md(quote.join("\n"))}</blockquote>`); quote = []; } };
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (/^>\s?/.test(l)) { closePara(); closeList(); quote.push(l.replace(/^>\s?/, "")); continue; }
      closeQuote();
      if (/^```/.test(l)) {
        closePara(); closeList();
        const code = [];
        while (++i < lines.length && !/^```/.test(lines[i])) code.push(lines[i]);
        out.push(`<pre><code>${esc(code.join("\n"))}</code></pre>`);
        continue;
      }
      if (!l.trim()) { closePara(); const nx = lines[i + 1] || ""; if (list && !/^\s+\S/.test(nx) && !/^\s*([-*]|\d+\.)\s/.test(nx)) closeList(); continue; }
      if (/^---+\s*$/.test(l)) { closePara(); closeList(); out.push("<hr>"); continue; }
      const h = l.match(/^(#{1,6})\s+(.*)$/);
      if (h) { closePara(); closeList(); const n = h[1].length <= 3 ? 3 : 4; out.push(`<h${n}>${inline(h[2])}</h${n}>`); continue; }
      if (/^\s*\|/.test(l)) {
        closePara(); closeList();
        const rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
        i--;
        const cells = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
        const [head, , ...body] = rows;
        out.push(`<table><thead><tr>${cells(head).map(c => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>${body.map(r => `<tr>${cells(r).map(c => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
        continue;
      }
      const li = l.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
      if (li) {
        closePara();
        const tag = /\d/.test(li[2]) ? "ol" : "ul";
        if (li[1].length >= 2 && list) { list.items[list.items.length - 1].sub.push(li[3]); continue; }
        if (!list || list.tag !== tag) { closeList(); list = { tag, items: [] }; }
        list.items.push({ text: li[3], sub: [] });
        continue;
      }
      // answer options ("   a) …") under a question keep their own line; other indented text is wrapping
      if (list && /^\s+\S/.test(l)) { list.items[list.items.length - 1].text += (/^\s+[a-h]\)\s/.test(l) ? "\u0001" : " ") + l.trim(); continue; }
      closeList();
      // "a) …", "b) …" on their own lines are answer options, not wrapped prose
      para.push((para.length && /^[a-h]\)\s/.test(l.trim()) ? "\u0001" : "") + l.trim());
    }
    closePara(); closeList(); closeQuote();
    return out.join("\n");
  }
  window.md = md;
})();
