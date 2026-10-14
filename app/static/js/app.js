// Small progressive enhancements. Pages work without this file; it adds the
// theme toggle, form helpers and auto-follow for the live debate view.
(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ---- Theme toggle -------------------------------------------------------
  const sunIcon = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const moonIcon = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  function syncThemeButtons() {
    const dark = document.documentElement.dataset.theme === "dark";
    $$("[data-theme-toggle]").forEach((btn) => {
      btn.innerHTML = dark ? sunIcon : moonIcon;
      btn.setAttribute("aria-pressed", String(dark));
    });
  }

  // ---- New debate form ----------------------------------------------------
  function updateCounter(el) {
    const out = $(el.dataset.counter);
    if (out) out.textContent = `${el.value.length} / ${el.maxLength}`;
  }
  function updateEstimate() {
    const out = $("#estimate");
    if (!out) return;
    const members = $$('input[name="agent_ids"]:checked').length;
    const rounds = Number(($('input[name="max_rounds"]:checked') || {}).value || 0);
    out.textContent = members < 2
      ? "Pick at least two council members."
      : `${members} members × ${rounds} round${rounds === 1 ? "" : "s"} = ${members * rounds} turns, plus the moderator's report.`;
  }

  // ---- Click actions ------------------------------------------------------
  document.addEventListener("click", async (e) => {
    if (e.target.closest("[data-theme-toggle]")) {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (err) { /* storage unavailable */ }
      syncThemeButtons();
      return;
    }

    if (e.target.closest("[data-history-back]")) {
      if (history.length > 1) history.back(); else location.href = "/";
      return;
    }

    const fill = e.target.closest("[data-fill-topic]");
    if (fill) {
      const topic = $("#topic");
      topic.value = fill.dataset.fillTopic;
      updateCounter(topic);
      topic.focus();
      return;
    }

    const selectAll = e.target.closest("[data-select-all]");
    if (selectAll) {
      const boxes = $$(`input[name="${selectAll.dataset.selectAll}"]`);
      const allOn = boxes.every((b) => b.checked);
      boxes.forEach((b) => (b.checked = !allOn));
      selectAll.textContent = allOn ? "Select all" : "Clear";
      updateEstimate();
      return;
    }

    const copy = e.target.closest("[data-copy]");
    if (copy) {
      const src = $(copy.dataset.copy);
      const text = src ? (src.content ? src.content.textContent : src.textContent) : "";
      try {
        await navigator.clipboard.writeText(text.trim());
        const original = copy.innerHTML;
        copy.textContent = "Copied!";
        setTimeout(() => (copy.innerHTML = original), 1500);
      } catch (err) { /* clipboard unavailable */ }
      return;
    }

    if (e.target.closest("[data-follow]")) {
      follow = true;
      window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    }
  });

  document.addEventListener("input", (e) => {
    if (e.target.matches("[data-counter]")) updateCounter(e.target);
  });
  document.addEventListener("change", (e) => {
    if (e.target.matches('input[name="agent_ids"], input[name="max_rounds"]')) updateEstimate();
  });

  // ---- Live chamber: keep the newest message in view -----------------------
  let follow = true;
  const nearBottom = () => window.innerHeight + window.scrollY >= document.body.scrollHeight - 200;
  window.addEventListener("scroll", () => {
    follow = nearBottom();
    const btn = $("[data-follow]");
    if (btn) btn.hidden = follow;
  }, { passive: true });
  document.addEventListener("htmx:sseMessage", () => {
    if (follow) window.scrollTo({ top: document.body.scrollHeight });
  });
  document.addEventListener("htmx:sseClose", () => {
    const btn = $("[data-follow]");
    if (btn) btn.remove();
  });

  // ---- Init ---------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", () => {
    syncThemeButtons();
    $$("[data-counter]").forEach(updateCounter);
    updateEstimate();
  });
})();
