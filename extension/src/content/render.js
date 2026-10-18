// Classic script (injected on toolbar click). DOM builders for the pet and result panel.
// All returned text is set with textContent / DOM APIs; nothing is parsed as HTML.
// Tested in Node via vm with a fake document (test/render.test.js).
(function (root) {
  "use strict";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const STATE_NAMES = ["idle", "searching", "finished", "error"];

  function el(doc, tag, opts, children) {
    const node = doc.createElement(tag);
    const o = opts || {};
    if (o.className) node.setAttribute("class", o.className);
    if (o.text !== undefined && o.text !== null) node.textContent = String(o.text);
    if (o.attrs) for (const k of Object.keys(o.attrs)) node.setAttribute(k, String(o.attrs[k]));
    for (const c of children || []) if (c) node.appendChild(c);
    return node;
  }

  function svg(doc, tag, attrs, children) {
    const node = doc.createElementNS(SVG_NS, tag);
    for (const k of Object.keys(attrs || {})) node.setAttribute(k, String(attrs[k]));
    for (const c of children || []) if (c) node.appendChild(c);
    return node;
  }

  /** Defense in depth: links were filtered in the service worker; check again before rendering. */
  function safeHref(value) {
    if (typeof value !== "string" || !value || value.length > 2048) return null;
    let url;
    try {
      url = new URL(value);
    } catch (e) {
      return null;
    }
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (url.username || url.password) return null;
    return url.href;
  }

  function link(doc, href, text) {
    const safe = safeHref(href);
    if (!safe) return el(doc, "span", { className: "nolink", text: text || "Link hidden (unsafe address)" });
    return el(doc, "a", {
      text: text || safe,
      attrs: { href: safe, target: "_blank", rel: "noopener noreferrer", referrerpolicy: "no-referrer" },
    });
  }

  function badge(doc, text, extra) {
    return el(doc, "span", { className: "badge" + (extra ? " " + extra : ""), text });
  }

  function sourceCite(doc, source) {
    if (!source) return null;
    return el(doc, "p", { className: "cite" }, [
      link(doc, source.href, source.text),
      source.unverified ? badge(doc, "Unverified source", "unverified") : null,
      source.kind ? el(doc, "span", { text: source.kind }) : null,
    ]);
  }

  function section(doc, title, children) {
    return el(doc, "div", { className: "section" }, [el(doc, "h3", { text: title })].concat(children));
  }

  function promiseRow(doc, p) {
    const quotes = p.quotes.map((q) =>
      el(doc, "div", { className: "quote" }, [el(doc, "blockquote", { text: q.text }), sourceCite(doc, q.source)]));
    let quoteBlock = null;
    if (quotes.length) {
      quoteBlock = el(doc, "details", {}, [el(doc, "summary", { text: `Quoted sources (${quotes.length})` })].concat(quotes));
      // Conflicts must show both sides without an extra click.
      if (p.status === "conflicting") quoteBlock.setAttribute("open", "");
    }
    return el(doc, "article", { className: "promise", attrs: { "data-status": p.status } }, [
      el(doc, "div", { className: "promise-head" }, [
        el(doc, "h4", { text: p.topic }),
        el(doc, "span", { className: "status-label", text: p.statusLabel }),
      ]),
      p.merchantStatement ? el(doc, "p", { text: `Merchant says: “${p.merchantStatement}”` }) : null,
      el(doc, "p", { text: p.explanation }),
      p.conditions ? el(doc, "p", { className: "note", text: p.conditions }) : null,
      quoteBlock,
    ]);
  }

  /** Builds the result panel body from a view-model produced by the service worker. */
  function renderPanel(doc, vm) {
    const panel = el(doc, "section", {
      className: "panel",
      attrs: { role: "dialog", "aria-label": "Seller check result", tabindex: "-1" },
    });
    const head = el(doc, "div", { className: "panel-head" }, [
      el(doc, "h2", { text: "Seller check result" }),
      badge(doc, vm.dataMode.label, vm.dataMode.isSimulation ? "sim" : ""),
    ]);
    panel.appendChild(head);
    panel.appendChild(el(doc, "p", { className: vm.dataMode.isSimulation ? "banner sim" : "banner info", text: vm.dataMode.note }));
    panel.appendChild(el(doc, "dl", { className: "verdict" }, [
      el(doc, "dt", { text: "Seller risk" }), el(doc, "dd", { text: vm.risk.label }),
      el(doc, "dt", { text: "Decision" }), el(doc, "dd", { text: vm.decision.label }),
    ]));
    panel.appendChild(el(doc, "p", { className: "summary", text: vm.summary }));
    if (vm.insufficient) {
      panel.appendChild(el(doc, "p", {
        className: "note",
        text: "The check finished, but the evidence found was not enough for a confident answer. This is a completed result, not an error.",
      }));
    }
    if (vm.missingInformation.length) {
      panel.appendChild(section(doc, "Still unknown", [
        el(doc, "ul", {}, vm.missingInformation.map((m) => el(doc, "li", { text: m }))),
      ]));
    }
    panel.appendChild(section(doc, "Research status", [
      el(doc, "ul", {}, vm.research.map((line) => el(doc, "li", { text: line }))),
    ]));
    if (vm.promises.length) {
      panel.appendChild(section(doc, "Merchant promises", vm.promises.map((p) => promiseRow(doc, p))));
    }
    if (vm.contexts.length) {
      panel.appendChild(section(doc, "Context", vm.contexts.map((c) =>
        el(doc, "div", { className: "context" }, [
          el(doc, "p", {}, [el(doc, "strong", { text: c.title + ": " }), el(doc, "span", { text: c.statusLabel })]),
          el(doc, "p", { className: "note", text: c.explanation }),
          c.source ? sourceCite(doc, c.source) : null,
        ]))));
    }
    if (vm.sources.length) {
      panel.appendChild(section(doc, "Sources", [
        el(doc, "ul", {}, vm.sources.map((s) => el(doc, "li", {}, [
          link(doc, s.href, s.text), doc.createTextNode(" "),
          badge(doc, s.badge, s.unverified ? "unverified" : ""),
          s.kind ? el(doc, "span", { className: "note", text: " " + s.kind }) : null,
        ]))),
      ]));
    } else {
      panel.appendChild(section(doc, "Sources", [el(doc, "p", { className: "note", text: "No source links were returned." })]));
    }
    panel.appendChild(el(doc, "p", { className: "disclaimer", text: vm.disclaimer }));
    return panel;
  }

  /** Code-native mascot: a small round-bottle mascot. No external assets. */
  function renderMascot(doc) {
    return svg(doc, "svg", { class: "mascot", viewBox: "0 0 64 64", "aria-hidden": "true", focusable: "false" }, [
      svg(doc, "g", { class: "body-group" }, [
        svg(doc, "rect", { x: 25, y: 3, width: 14, height: 9, rx: 2, fill: "#5b3f96" }),
        svg(doc, "rect", { x: 28, y: 12, width: 8, height: 7, fill: "#b9a6dd" }),
        svg(doc, "rect", { x: 10, y: 18, width: 44, height: 40, rx: 13, fill: "#efe6ff", stroke: "#5b3f96", "stroke-width": 2.5 }),
        svg(doc, "path", { d: "M16 26 Q18 22 24 21", stroke: "#ffffff", "stroke-width": 3, fill: "none", "stroke-linecap": "round" }),
        svg(doc, "g", { class: "eyes" }, [
          svg(doc, "circle", { cx: 25, cy: 36, r: 3.6, fill: "#1f1a2e" }),
          svg(doc, "circle", { cx: 39, cy: 36, r: 3.6, fill: "#1f1a2e" }),
        ]),
        svg(doc, "path", { class: "mouth-smile", d: "M26 45 Q32 50 38 45", stroke: "#1f1a2e", "stroke-width": 2.2, fill: "none", "stroke-linecap": "round" }),
        svg(doc, "path", { class: "mouth-puzzled", d: "M26 47 Q29 44 32 47 T38 47", stroke: "#1f1a2e", "stroke-width": 2.2, fill: "none", "stroke-linecap": "round" }),
        svg(doc, "circle", { cx: 18, cy: 43, r: 3, fill: "#f7b6c8", opacity: 0.8 }),
        svg(doc, "circle", { cx: 46, cy: 43, r: 3, fill: "#f7b6c8", opacity: 0.8 }),
      ]),
      svg(doc, "g", { class: "glass" }, [
        svg(doc, "circle", { cx: 52, cy: 40, r: 7, fill: "rgba(255,255,255,0.6)", stroke: "#5b3f96", "stroke-width": 2.5 }),
        svg(doc, "line", { x1: 47, y1: 46, x2: 41, y2: 53, stroke: "#5b3f96", "stroke-width": 3, "stroke-linecap": "round" }),
      ]),
      (function () {
        const t = svg(doc, "text", { class: "qmark", x: 50, y: 14, "font-size": 16, "font-weight": 700, fill: "#9c1c1c", "font-family": "sans-serif" });
        t.textContent = "?";
        return t;
      })(),
      svg(doc, "g", { class: "alert" }, [
        svg(doc, "circle", { cx: 54, cy: 10, r: 8, fill: "#5b3f96" }),
        (function () {
          const t = svg(doc, "text", { x: 54, y: 14.5, "text-anchor": "middle", "font-size": 12, "font-weight": 700, fill: "#ffffff", "font-family": "sans-serif" });
          t.textContent = "!";
          return t;
        })(),
      ]),
    ]);
  }

  function prefersReducedMotion(win) {
    try {
      return Boolean(win && typeof win.matchMedia === "function" && win.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (e) {
      return false;
    }
  }

  /** Content-side check: state pushes must come from this extension's service worker (no tab). */
  function isTrustedWorkerSender(sender, runtimeId) {
    return Boolean(sender && runtimeId && sender.id === runtimeId && !sender.tab);
  }

  function isValidStateMessage(msg) {
    if (!msg || typeof msg !== "object" || msg.type !== "state") return false;
    const s = msg.state;
    if (!s || typeof s !== "object" || STATE_NAMES.indexOf(s.name) === -1) return false;
    if (s.name === "finished" && (!s.viewModel || typeof s.viewModel !== "object")) return false;
    if (s.name === "error" && (!s.error || typeof s.error.message !== "string")) return false;
    return true;
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), Math.max(min, max));
  }

  root.VIZS_RENDER = {
    el, svg, safeHref, link, renderPanel, renderMascot, prefersReducedMotion,
    isTrustedWorkerSender, isValidStateMessage, clamp,
  };
})(globalThis);
