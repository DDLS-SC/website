/*
  Search and filters for list pages (Research, Collaborate, People).

  Markup:
    <div data-filter-root>
      <input type="search" data-filter="q">            free-text search over each item's data-search
      <select data-filter="site">…</select>            matches the item's data-site
      <button data-filter="type" data-value="…">        chip; clicking toggles it (one per group)
      <span data-count></span>                          "Showing 3 of 8"
      <section data-group> … items … </section>          hidden when none of its items match
      <li data-item data-site="…" data-type="…" data-search="…">
      <p data-empty hidden>                              shown when nothing matches
      <time data-expires="2027-01-31">                  (optional) item hidden after this date
    </div>

  Without JavaScript every item stays visible.
*/
(function () {
  var today = new Date().toISOString().slice(0, 10);

  document.querySelectorAll("[data-filter-root]").forEach(function (root) {
    var items = Array.prototype.slice.call(root.querySelectorAll("[data-item]"));
    var groups = root.querySelectorAll("[data-group]");
    var count = root.querySelector("[data-count]");
    var empty = root.querySelector("[data-empty]");
    var controls = root.querySelectorAll("[data-filter]");
    var state = {};

    // Drop posts that have expired since the site was last built.
    items = items.filter(function (item) {
      var exp = item.getAttribute("data-expires");
      if (exp && exp < today) { item.remove(); return false; }
      return true;
    });

    function norm(s) { return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, ""); }

    function apply() {
      var shown = 0;
      var words = norm(state.q).split(/\s+/).filter(Boolean);
      items.forEach(function (item) {
        var ok = true;
        Object.keys(state).forEach(function (key) {
          if (key === "q" || !state[key]) return;
          var values = (item.getAttribute("data-" + key) || "").split("|");
          if (values.indexOf(state[key]) < 0) ok = false;
        });
        if (ok && words.length) {
          var text = norm(item.getAttribute("data-search"));
          ok = words.every(function (w) { return text.indexOf(w) >= 0; });
        }
        item.hidden = !ok;
        if (ok) shown++;
      });
      groups.forEach(function (g) { g.hidden = !g.querySelector("[data-item]:not([hidden])"); });
      if (count) count.textContent = shown === items.length ? items.length + " shown" : "Showing " + shown + " of " + items.length;
      if (empty) empty.hidden = shown > 0;
    }

    controls.forEach(function (el) {
      var key = el.getAttribute("data-filter");
      if (el.tagName === "BUTTON") {
        el.setAttribute("aria-pressed", el.classList.contains("is-active") ? "true" : "false");
        el.addEventListener("click", function () {
          var value = el.getAttribute("data-value") || "";
          var same = state[key] === value;
          state[key] = same ? "" : value;
          root.querySelectorAll('button[data-filter="' + key + '"]').forEach(function (b) {
            var on = !same && b === el || (!state[key] && !b.getAttribute("data-value"));
            b.classList.toggle("is-active", on);
            b.setAttribute("aria-pressed", on ? "true" : "false");
          });
          apply();
        });
      } else {
        el.addEventListener("input", function () { state[key] = el.value; apply(); });
      }
    });

    // Clicking a skill or tag fills in the search box.
    root.querySelectorAll("[data-search-for]").forEach(function (el) {
      el.addEventListener("click", function () {
        var box = root.querySelector('[data-filter="q"]');
        if (!box) return;
        box.value = el.getAttribute("data-search-for");
        state.q = box.value;
        apply();
        box.focus();
      });
    });

    root.classList.add("filters-ready");
    apply();
  });
})();
