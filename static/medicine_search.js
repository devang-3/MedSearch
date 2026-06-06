(function () {
  const input = document.getElementById("searchInput");
  const combinedList = document.getElementById("combinedList");
  const clearBtn = document.getElementById("clearBtn");
  const statusEl = document.getElementById("status");
  const algoPanels = document.getElementById("algoPanels");
  const searchBox = document.getElementById("searchBox");
  const alternativesPanel = document.getElementById("alternativesPanel");
  const selectedNameEl = document.getElementById("selectedName");
  const selectedCompositionEl = document.getElementById("selectedComposition");
  const selectedPackEl = document.getElementById("selectedPack");
  const selectedPriceEl = document.getElementById("selectedPrice");
  const selectedFormLabelEl = document.getElementById("selectedFormLabel");
  const sameFormFilter = document.getElementById("sameFormFilter");
  const altCountEl = document.getElementById("altCount");
  const alternativesList = document.getElementById("alternativesList");

  const ALGO_IDS = [
    "prefix",
    "fuzzy_ngram",
    "keyboard_dl",
    "double_metaphone",
    "substring",
  ];

  let debounceTimer = null;
  let activeIndex = -1;
  let lastCombined = [];
  let requestId = 0;
  let altRequestId = 0;
  let selectedMedicineName = "";

  function setStatus(text, loading) {
    statusEl.textContent = text;
    statusEl.classList.toggle("loading", !!loading);
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function renderCombined(items) {
    lastCombined = items;
    activeIndex = -1;
    if (!items.length) {
      combinedList.hidden = true;
      combinedList.innerHTML = "";
      return;
    }
    combinedList.hidden = false;
    combinedList.innerHTML = items
      .map(
        (item, i) =>
          `<li role="option" data-index="${i}" data-name="${escapeHtml(item.name)}">
            <span class="name">${escapeHtml(item.name)}</span>
            <span class="meta"><span class="src">${escapeHtml(item.source)}</span> · ${escapeHtml(item.detail || "")}</span>
          </li>`
      )
      .join("");
  }

  function renderAlgoPanel(key, items) {
    const ul = document.getElementById(`list-${key}`);
    if (!ul) return;
    if (!items || !items.length) {
      ul.innerHTML = '<li class="empty">No matches</li>';
      return;
    }
    ul.innerHTML = items
      .map(
        (item) =>
          `<li data-name="${escapeHtml(item.name)}">
            ${escapeHtml(item.name)}
            ${item.detail ? `<span class="detail">${escapeHtml(item.detail)}</span>` : ""}
          </li>`
      )
      .join("");
  }

  function hideAlternatives() {
    alternativesPanel.hidden = true;
    altRequestId++;
    selectedMedicineName = "";
  }

  function formatPriceDisplay(priceDisplay, price) {
    if (priceDisplay) return priceDisplay;
    if (price != null && !Number.isNaN(Number(price))) {
      return `₹${Number(price).toFixed(2)}`;
    }
    return "";
  }

  function renderAlternatives(data) {
    if (!data.found) {
      selectedNameEl.textContent = data.selected;
      selectedCompositionEl.textContent = "Medicine not found in dataset.";
      selectedPackEl.textContent = "";
      selectedPriceEl.textContent = "";
      selectedFormLabelEl.textContent = "—";
      altCountEl.textContent = "";
      alternativesList.innerHTML = "";
      alternativesPanel.hidden = false;
      return;
    }

    selectedNameEl.textContent = data.selected;
    selectedCompositionEl.textContent = data.composition
      ? `Composition: ${data.composition}`
      : "Composition: not available";
    selectedPackEl.textContent = data.pack_size_label
      ? `Pack: ${data.pack_size_label}`
      : "";
    const priceText = formatPriceDisplay(data.price_display, data.price);
    selectedPriceEl.textContent = priceText ? `Price: ${priceText}` : "";
    selectedFormLabelEl.textContent = data.form_label || data.form || "—";
    if (sameFormFilter) {
      sameFormFilter.checked = data.same_form !== false;
    }

    const total = data.same_form
      ? (data.total_matching_form ?? data.alternatives.length)
      : (data.total_alternatives ?? data.alternatives.length);
    const shown = data.alternatives.length;
    const filterNote = data.same_form ? " (same form)" : " (all forms)";
    altCountEl.textContent = total
      ? `${total} alternative(s) found${filterNote}${shown < total ? ` — showing ${shown}` : ""}`
      : data.same_form
        ? "No alternatives with the same composition, dosage, and form."
        : "No alternatives with the same composition and dosage.";

    if (!data.alternatives.length) {
      alternativesList.innerHTML = '<li class="empty">No alternatives found</li>';
    } else {
      alternativesList.innerHTML = data.alternatives
        .map((alt) => {
          const altPrice = formatPriceDisplay(alt.price_display, alt.price);
          const formBadge = alt.form_label ? `<span class="form-badge">${escapeHtml(alt.form_label)}</span>` : "";
          const priceBadge = altPrice ? `<span class="price-badge">${escapeHtml(altPrice)}</span>` : "";
          return `<li data-name="${escapeHtml(alt.name)}">
              <span class="alt-row-top">
                <span class="name">${escapeHtml(alt.name)}</span>
                ${priceBadge}
              </span>
              <span class="meta">${formBadge}${formBadge && alt.pack_size_label ? " · " : ""}${escapeHtml(alt.pack_size_label || "")}</span>
            </li>`;
        })
        .join("");
    }
    alternativesPanel.hidden = false;
  }

  async function fetchAlternatives(name) {
    selectedMedicineName = name;
    const id = ++altRequestId;
    alternativesPanel.hidden = false;
    selectedNameEl.textContent = name;
    selectedCompositionEl.textContent = "Loading alternatives…";
    selectedPackEl.textContent = "";
    selectedPriceEl.textContent = "";
    altCountEl.textContent = "";
    alternativesList.innerHTML = "";

    try {
      const params = new URLSearchParams({
        name,
        limit: "20",
        same_form: sameFormFilter && sameFormFilter.checked ? "1" : "0",
      });
      const res = await fetch(`/api/alternatives?${params}`);
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      if (id !== altRequestId) return;
      renderAlternatives(data);
    } catch (err) {
      if (id !== altRequestId) return;
      selectedCompositionEl.textContent = `Error: ${err.message}`;
      alternativesList.innerHTML = "";
    }
  }

  function applySelection(name) {
    input.value = name;
    combinedList.hidden = true;
    clearBtn.hidden = false;
    fetchAlternatives(name);
  }

  async function fetchSuggestions(q) {
    const id = ++requestId;
    setStatus("Searching…", true);
    try {
      const params = new URLSearchParams({ q, per_algo: "8", combined: "10" });
      const res = await fetch(`/api/suggest?${params}`);
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      if (id !== requestId) return;

      renderCombined(data.combined || []);
      ALGO_IDS.forEach((key) => {
        renderAlgoPanel(key, (data.algorithms && data.algorithms[key]) || []);
      });

      const total = (data.combined || []).length;
      if (!q.trim()) {
        algoPanels.hidden = true;
        setStatus("Type to search — suggestions update as you type.");
      } else {
        algoPanels.hidden = false;
        setStatus(
          total
            ? `${total} combined suggestion(s) for “${data.query}”`
            : `No matches for “${data.query}”`
        );
      }
    } catch (err) {
      if (id !== requestId) return;
      setStatus(`Error: ${err.message}`);
      combinedList.hidden = true;
    }
  }

  function scheduleSearch() {
    const q = input.value.trim();
    clearBtn.hidden = !q;
    if (debounceTimer) clearTimeout(debounceTimer);
    if (!q) {
      requestId++;
      combinedList.hidden = true;
      algoPanels.hidden = true;
      hideAlternatives();
      ALGO_IDS.forEach((k) => renderAlgoPanel(k, []));
      setStatus("Type to search — suggestions update as you type.");
      return;
    }
    debounceTimer = setTimeout(() => fetchSuggestions(q), 280);
  }

  input.addEventListener("input", scheduleSearch);

  input.addEventListener("keydown", (e) => {
    const items = combinedList.querySelectorAll("li[role=option]");
    if (!items.length || combinedList.hidden) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      applySelection(lastCombined[activeIndex].name);
      return;
    } else if (e.key === "Escape") {
      combinedList.hidden = true;
      return;
    } else {
      return;
    }

    items.forEach((li, i) => li.classList.toggle("active", i === activeIndex));
    if (activeIndex >= 0) {
      items[activeIndex].scrollIntoView({ block: "nearest" });
    }
  });

  combinedList.addEventListener("click", (e) => {
    const li = e.target.closest("li[role=option]");
    if (!li) return;
    applySelection(li.dataset.name);
  });

  document.querySelectorAll(".panel-list").forEach((ul) => {
    ul.addEventListener("click", (e) => {
      const li = e.target.closest("li[data-name]");
      if (!li || li.classList.contains("empty")) return;
      applySelection(li.dataset.name);
    });
  });

  clearBtn.addEventListener("click", () => {
    input.value = "";
    clearBtn.hidden = true;
    hideAlternatives();
    scheduleSearch();
    input.focus();
  });

  alternativesList.addEventListener("click", (e) => {
    const li = e.target.closest("li[data-name]");
    if (!li || li.classList.contains("empty")) return;
    applySelection(li.dataset.name);
  });

  sameFormFilter.addEventListener("change", () => {
    if (selectedMedicineName) {
      fetchAlternatives(selectedMedicineName);
    }
  });

  document.addEventListener("click", (e) => {
    if (!searchBox.contains(e.target)) {
      combinedList.hidden = true;
    }
  });

  input.focus();
})();
