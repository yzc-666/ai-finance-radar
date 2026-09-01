(() => {
  "use strict";

  document.documentElement.classList.add("js");
  const script = document.querySelector("script[data-radar-app]");
  const root = script?.src ? new URL("../../", script.src) : new URL("./", document.baseURI);
  const page = document.body?.dataset.page || "";
  const collator = new Intl.Collator("en", { numeric: true, sensitivity: "base" });
  const numbers = new Intl.NumberFormat("en-US");
  const dates = new Intl.DateTimeFormat("en", { day: "numeric", month: "short", timeZone: "UTC", year: "numeric" });
  const dateTimes = new Intl.DateTimeFormat("en", {
    day: "numeric", hour: "2-digit", hour12: false, minute: "2-digit",
    month: "short", timeZone: "UTC", timeZoneName: "short", year: "numeric",
  });
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
  const array = (value) => (Array.isArray(value) ? value : []);
  const text = (value) => (value == null ? "" : String(value));
  const escape = (value) => text(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
  const local = (path) => new URL(text(path).replace(/^\/+/, ""), root).href;

  function webUrl(value) {
    try {
      const url = new URL(text(value));
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch {
      return "";
    }
  }

  function slug(value) {
    return text(value).normalize("NFKD").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "record";
  }

  function label(value) {
    return text(value).replace(/[_-]+/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
  }

  function country(value) {
    const normalized = text(value).trim().toLowerCase();
    if (["cn", "china", "people's republic of china"].includes(normalized)) return "CN";
    if (["us", "usa", "united states", "united states of america"].includes(normalized)) return "US";
    return text(value).toUpperCase();
  }

  function countryName(value) {
    return { CN: "China", US: "United States" }[country(value)] || text(value);
  }

  function tier(value) {
    const raw = text(value).trim();
    const match = raw.match(/(?:tier[\s_-]*)?([123])$/i);
    if (match) return `Tier ${match[1]}`;
    if (raw.toLowerCase() === "primary") return "Tier 1";
    if (raw.toLowerCase() === "secondary") return "Tier 2";
    return raw ? label(raw) : "Source tier unavailable";
  }

  function confidence(value) {
    if (value === "" || value == null) return "";
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "";
    const percentage = parsed >= 0 && parsed <= 1 ? parsed * 100 : parsed;
    return `${Math.round(Math.max(0, Math.min(100, percentage)))}% confidence`;
  }

  function milliseconds(value) {
    const parsed = Date.parse(text(value));
    return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
  }

  function formatDate(value, includeTime = false) {
    const parsed = milliseconds(value);
    if (!Number.isFinite(parsed)) return "Unknown";
    const formatter = includeTime && /T\d{2}:\d{2}/.test(text(value)) ? dateTimes : dates;
    return formatter.format(new Date(parsed));
  }

  function mostRecent(values) {
    return values.filter(Boolean).sort((left, right) => milliseconds(right) - milliseconds(left))[0] || "";
  }

  function unpack(payload, key) {
    const records = Array.isArray(payload) ? payload : array(payload?.[key]);
    return {
      records,
      updatedAt: payload?.updated_at || payload?.generated_at || mostRecent(records.flatMap((record) => [
        record.retrieved_at, record.last_verified_at, record.verification?.verified_at, record.published_at,
      ])),
    };
  }

  function companyRecord(company) {
    const homepage = company.homepage || company.official_homepage || "";
    let sourceRows = array(company.sources);
    if (!sourceRows.length) sourceRows = array(company.provenance);
    if (!sourceRows.length) {
      sourceRows = array(company.source_urls).map((url) => ({ url, publisher: company.name, tier: "primary" }));
    }
    return {
      ...company,
      country: country(company.country || array(company.jurisdictions)[0]),
      homepage,
      last_verified_at: company.last_verified_at || company.verification?.verified_at || "",
      one_liner: company.one_liner || company.description || "",
      products: array(company.products).map((product) => ({
        ...product,
        note: product.note || product.description || product.category || "",
        url: product.url || homepage,
      })),
      sectors: array(company.sectors),
      slug: company.slug || slug(company.name || company.id),
      sources: sourceRows.map((source) => ({
        ...source,
        publisher: source.publisher || company.name || "Official source",
        tier: source.tier ?? source.source_tier ?? source.source_class ?? "primary",
      })),
      verification_status: company.verification_status || company.verification?.status || "verified",
    };
  }

  function eventRecord(event) {
    const primary = event.primary_source || {};
    const canonicalSource = event.source && typeof event.source === "object" ? event.source : {};
    const fallback = text(event.slug || event.id).replace(/^evt-\d{4}-\d{2}-\d{2}-/, "").replace(/^evt-/, "");
    const title = event.title || canonicalSource.title || primary.title || label(fallback);
    return {
      ...event,
      company_ids: array(event.company_ids),
      content_hash: event.content_sha256 || event.content_hash || event.sha256 || "",
      country: country(event.country || array(event.jurisdictions)[0]),
      published_at: event.published_at || primary.published_on || event.event_date,
      publisher: canonicalSource.publisher || event.publisher || primary.publisher || "Official source",
      primary_url: canonicalSource.url || event.primary_url || primary.url || "",
      retrieved_at: event.retrieved_at || event.retrieval?.retrieved_at || "",
      sectors: array(event.sectors),
      slug: event.slug || slug(title || event.id),
      source_class: canonicalSource.source_class || event.source_class || "",
      source_title: canonicalSource.title || event.source_title || primary.title || "",
      source_tier: event.source_tier ?? canonicalSource.source_tier ?? primary.source_tier ?? canonicalSource.source_class ?? "primary",
      summary: event.summary || "",
      title,
      type: event.type || event.event_type || "event",
      verification_status:
        event.verification_status ||
        (event.status === "published" || event.verification ? "verified" : event.status) ||
        "unverified",
    };
  }

  async function dataset(path, key, normalize) {
    const response = await fetch(local(path), {
      cache: "no-cache", credentials: "same-origin", headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}`);
    const parsed = unpack(await response.json(), key);
    return { records: parsed.records.map(normalize), updatedAt: parsed.updatedAt };
  }

  function verified(record) {
    return ["verified", "published", "primary-source"].includes(text(record.verification_status).trim().toLowerCase());
  }

  function setText(selector, value) {
    const target = $(selector);
    if (target) target.textContent = value;
  }

  function setStatus(message, state) {
    const target = $("[data-data-status]");
    if (!target) return;
    target.textContent = message;
    target.dataset.state = state;
  }

  function setUpdated(value) {
    $$("[data-footer-updated]").forEach((target) => { target.textContent = formatDate(value, true); });
  }

  function emptyState(title, message, path = "") {
    const dataLink = path
      ? ` You can inspect <a href="${escape(local(path))}">${escape(path.split("/").pop())}</a> directly.`
      : "";
    return `<div class="state-panel"><h3>${escape(title)}</h3><p>${escape(message)}${dataLink}</p></div>`;
  }

  function populate(select, values, firstLabel, formatter = label) {
    if (!select) return;
    select.replaceChildren();
    const first = document.createElement("option");
    first.value = "";
    first.textContent = firstLabel;
    select.append(first);
    [...new Set(values.map(text).filter(Boolean))].sort(collator.compare).forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = formatter(value);
      select.append(option);
    });
  }

  function readQuery(form, attribute, fields) {
    const params = new URLSearchParams(location.search);
    fields.forEach((field) => {
      const control = $(`[${attribute}="${field}"]`, form);
      if (!control) return;
      const requested = params.get(field) || "";
      control.value = control instanceof HTMLSelectElement &&
        ![...control.options].some((option) => option.value === requested) ? "" : requested;
    });
  }

  function writeQuery(form, attribute, fields) {
    const url = new URL(location.href);
    fields.forEach((field) => {
      const value = text($(`[${attribute}="${field}"]`, form)?.value).trim();
      if (value) url.searchParams.set(field, value);
      else url.searchParams.delete(field);
    });
    try {
      history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    } catch {
      // Filtering still works in restrictive file:// previews.
    }
  }

  function focusHash(kind) {
    if (!location.hash) return;
    let raw;
    try {
      raw = decodeURIComponent(location.hash.slice(1));
    } catch {
      raw = location.hash.slice(1);
    }
    const value = raw.includes("/") ? raw.slice(raw.indexOf("/") + 1) : raw;
    const target = [raw, value, `${kind}-${slug(value)}`].map((id) => document.getElementById(id)).find(Boolean) ||
      $$("[data-record-id]").find((card) => card.dataset.recordId === value);
    if (!target) return;
    $$(".is-deep-linked").forEach((card) => card.classList.remove("is-deep-linked"));
    target.classList.add("is-deep-linked");
    target.tabIndex = -1;
    requestAnimationFrame(() => {
      target.focus({ preventScroll: true });
      target.scrollIntoView({
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "center",
      });
    });
  }

  function initNavigation() {
    const toggle = $("[data-nav-toggle]");
    const nav = $("[data-nav]");
    if (!toggle || !nav) return;
    const close = () => {
      toggle.setAttribute("aria-expanded", "false");
      nav.dataset.open = "false";
    };
    close();
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", text(open));
      nav.dataset.open = text(open);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        close();
        toggle.focus();
      }
    });
    document.addEventListener("click", (event) => {
      if (!toggle.contains(event.target) && !nav.contains(event.target)) close();
    });
    nav.addEventListener("click", (event) => {
      if (event.target.closest("a")) close();
    });
  }

  function eventCard(event, companies) {
    const eventSlug = event.slug || event.id;
    const organizations = event.company_ids.map((id) => companies.get(text(id))).filter(Boolean)
      .map((company) => `<a href="${escape(local(`companies/${encodeURIComponent(company.slug || company.id)}.html`))}">${escape(company.name)}</a>`)
      .join('<span aria-hidden="true">·</span>') || '<span class="muted">Organization not listed</span>';
    const source = webUrl(event.primary_url);
    const score = confidence(event.confidence_score);
    return `<article class="event-card" id="event-${escape(slug(eventSlug))}" data-record-id="${escape(event.id)}">
      <div class="event-date-block"><time datetime="${escape(event.event_date)}">${escape(formatDate(event.event_date))}</time><span class="event-type">${escape(label(event.type))}</span></div>
      <div><div class="event-card-header"><h3><a href="${escape(local(`events/${encodeURIComponent(eventSlug)}.html`))}">${escape(event.title)}</a></h3><span class="badge badge-country" title="${escape(countryName(event.country))}">${escape(event.country)}</span></div>
      <div class="event-companies">${organizations}</div><p class="event-summary">${escape(event.summary)}</p>${event.context ? `<p class="event-context"><strong>Context</strong> ${escape(event.context)}</p>` : ""}
      <div class="chip-list" aria-label="Sectors">${event.sectors.map((sector) => `<span class="chip">${escape(sector)}</span>`).join("")}</div>
      <footer class="event-footer"><div class="event-source-meta"><span class="badge badge-verified">Verified</span><span class="source-tier">${escape(tier(event.source_tier))}</span>${score ? `<span class="source-tier">${escape(score)}</span>` : ""}</div>
      ${source ? `<a class="source-link" href="${escape(source)}" target="_blank" rel="noopener noreferrer">${escape(event.source_title || "Primary source")} · ${escape(event.publisher)} <span aria-hidden="true">↗</span></a>` : '<span class="source-tier">Primary URL unavailable</span>'}</footer></div>
    </article>`;
  }

  function landscape(events, selected, choose) {
    const target = $("[data-sector-landscape]");
    if (!target) return;
    const counts = new Map();
    events.forEach((event) => new Set(event.sectors).forEach((sector) => counts.set(sector, (counts.get(sector) || 0) + 1)));
    const rows = [...counts].sort((left, right) => right[1] - left[1] || collator.compare(left[0], right[0]));
    if (!rows.length) {
      target.innerHTML = '<p class="muted">No sector coverage is available yet.</p>';
      return;
    }
    const maximum = rows[0][1];
    target.innerHTML = rows.map(([sector, count]) =>
      `<button class="landscape-row" type="button" data-sector-value="${escape(sector)}" aria-pressed="${sector === selected}" style="--coverage:${Math.max(8, Math.round(count / maximum * 100))}%"><span>${escape(sector)}</span><strong>${numbers.format(count)}</strong></button>`,
    ).join("");
    $$("[data-sector-value]", target).forEach((button) => {
      button.addEventListener("click", () => choose(button.dataset.sectorValue || ""));
    });
  }

  async function initEvents() {
    const list = $("[data-event-list]");
    const form = $("[data-event-filters]");
    if (!list || !form) return;
    try {
      const [eventData, companyData] = await Promise.all([
        dataset("data/events.json", "events", eventRecord),
        dataset("data/companies.json", "companies", companyRecord),
      ]);
      const companies = companyData.records.sort((a, b) => collator.compare(a.name, b.name));
      const companyMap = new Map(companies.map((company) => [text(company.id), company]));
      const events = eventData.records.filter(verified).sort((a, b) =>
        milliseconds(b.event_date) - milliseconds(a.event_date) || collator.compare(a.slug, b.slug),
      );
      const updatedAt = mostRecent([eventData.updatedAt, companyData.updatedAt]);
      populate($('[data-filter="country"]', form), events.map((event) => event.country), "All countries", (code) => `${countryName(code)} (${code})`);
      populate($('[data-filter="type"]', form), events.map((event) => event.type), "All event types");
      populate($('[data-filter="sector"]', form), events.flatMap((event) => event.sectors), "All sectors", text);
      readQuery(form, "data-filter", ["q", "country", "type", "sector"]);
      setText('[data-stat="events"]', numbers.format(events.length));
      setText('[data-stat="companies"]', numbers.format(companies.length));
      setText('[data-stat="sources"]', numbers.format(new Set(events.map((event) => webUrl(event.primary_url)).filter(Boolean)).size));
      setText('[data-stat="updated"]', formatDate(updatedAt, true));
      setUpdated(updatedAt);
      setStatus("Local data loaded", "ready");

      const render = () => {
        const search = text($('[data-filter="q"]', form)?.value).trim().toLowerCase();
        const selectedCountry = text($('[data-filter="country"]', form)?.value);
        const selectedType = text($('[data-filter="type"]', form)?.value);
        const selectedSector = text($('[data-filter="sector"]', form)?.value);
        const matches = events.filter((event) => {
          const names = event.company_ids.map((id) => companyMap.get(text(id))?.name || id);
          const haystack = [event.title, event.summary, event.context, event.publisher, ...names, ...event.sectors].join(" ").toLowerCase();
          return (!search || haystack.includes(search)) &&
            (!selectedCountry || event.country === selectedCountry) &&
            (!selectedType || event.type === selectedType) &&
            (!selectedSector || event.sectors.includes(selectedSector));
        });
        setText("[data-result-count]", `${numbers.format(matches.length)} ${matches.length === 1 ? "record" : "records"}`);
        list.innerHTML = matches.length ? matches.map((event) => eventCard(event, companyMap)).join("") :
          emptyState("No verified events match", "Try a broader search or reset one of the filters.");
        list.setAttribute("aria-busy", "false");
        writeQuery(form, "data-filter", ["q", "country", "type", "sector"]);
        landscape(events, selectedSector, (value) => {
          const select = $('[data-filter="sector"]', form);
          select.value = select.value === value ? "" : value;
          render();
        });
        focusHash("event");
      };
      form.addEventListener("input", render);
      form.addEventListener("change", render);
      $("[data-filter-reset]", form)?.addEventListener("click", () => {
        form.reset();
        render();
        $('[data-filter="q"]', form)?.focus();
      });
      addEventListener("hashchange", () => focusHash("event"));
      render();
    } catch (error) {
      console.error("Unable to initialize event feed:", error);
      list.innerHTML = emptyState("The event feed is unavailable", "The local dataset could not be loaded. When previewing locally, use a web server.", "data/events.json");
      list.setAttribute("aria-busy", "false");
      setText("[data-result-count]", "Unavailable");
      setStatus("Data unavailable", "error");
      $$("input, select, button", form).forEach((control) => { control.disabled = true; });
    }
  }

  function companyCard(company) {
    const homepage = webUrl(company.homepage);
    const products = company.products.map((product) => {
      const url = webUrl(product.url) || homepage;
      return `<li><a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(product.name)} <span aria-hidden="true">↗</span></a><span>${escape(product.note || "Official product page")}</span></li>`;
    }).join("") || '<li><span class="muted">No public product record yet.</span></li>';
    const sources = company.sources.map((source) => {
      const url = webUrl(source.url);
      return url ? `<li><a href="${escape(url)}" target="_blank" rel="noopener noreferrer"><span>${escape(source.title || source.publisher)}</span><small>${escape(source.publisher)} · ${escape(tier(source.tier))} ↗</small></a></li>` : "";
    }).join("") || '<li><span class="muted">No source links listed.</span></li>';
    return `<article class="company-card" id="company-${escape(slug(company.slug))}" data-record-id="${escape(company.id)}">
      <div class="company-card-header"><div class="company-title-wrap"><h3><a href="${escape(local(`companies/${encodeURIComponent(company.slug || company.id)}.html`))}">${escape(company.name)}</a></h3><a class="official-link" href="${escape(homepage)}" target="_blank" rel="noopener noreferrer">Official homepage <span aria-hidden="true">↗</span></a></div><span class="badge badge-country" title="${escape(countryName(company.country))}">${escape(company.country)}</span></div>
      <p class="company-one-liner">${escape(company.one_liner)}</p><div class="chip-list" aria-label="Sectors">${company.sectors.map((sector) => `<span class="chip">${escape(sector)}</span>`).join("")}</div>
      <section class="company-products" aria-label="Official products"><h4>Official products</h4><ul class="product-list">${products}</ul></section>
      <section class="company-evidence" aria-label="Company evidence"><h4>Source evidence</h4><ul class="source-list">${sources}</ul></section>
      <footer class="company-card-footer"><span class="badge${verified(company) ? " badge-verified" : ""}">${escape(verified(company) ? "Verified" : label(company.verification_status))}</span><a class="profile-link" href="${escape(local(`companies/${encodeURIComponent(company.slug || company.id)}.html`))}">View evidence profile →</a></footer>
    </article>`;
  }

  async function initCompanies() {
    const list = $("[data-company-list]");
    const form = $("[data-company-filters]");
    if (!list || !form) return;
    try {
      const data = await dataset("data/companies.json", "companies", companyRecord);
      const companies = data.records.sort((a, b) => collator.compare(a.name, b.name));
      populate($('[data-company-filter="country"]', form), companies.map((company) => company.country), "All countries", (code) => `${countryName(code)} (${code})`);
      populate($('[data-company-filter="sector"]', form), companies.flatMap((company) => company.sectors), "All sectors", text);
      readQuery(form, "data-company-filter", ["q", "country", "sector"]);
      setText('[data-company-stat="companies"]', numbers.format(companies.length));
      setText('[data-company-stat="products"]', numbers.format(companies.reduce((total, company) => total + company.products.length, 0)));
      setText('[data-company-stat="sectors"]', numbers.format(new Set(companies.flatMap((company) => company.sectors)).size));
      setText('[data-company-stat="updated"]', formatDate(data.updatedAt, true));
      setUpdated(data.updatedAt);
      setStatus("Local data loaded", "ready");

      const render = () => {
        const search = text($('[data-company-filter="q"]', form)?.value).trim().toLowerCase();
        const selectedCountry = text($('[data-company-filter="country"]', form)?.value);
        const selectedSector = text($('[data-company-filter="sector"]', form)?.value);
        const matches = companies.filter((company) => {
          const haystack = [company.name, company.one_liner, ...company.sectors, ...company.products.flatMap((product) => [product.name, product.note])].join(" ").toLowerCase();
          return (!search || haystack.includes(search)) &&
            (!selectedCountry || company.country === selectedCountry) &&
            (!selectedSector || company.sectors.includes(selectedSector));
        });
        setText("[data-company-result-count]", `${numbers.format(matches.length)} ${matches.length === 1 ? "company" : "companies"}`);
        list.innerHTML = matches.length ? matches.map(companyCard).join("") :
          emptyState("No companies match", "Try a broader search or reset one of the filters.");
        list.setAttribute("aria-busy", "false");
        writeQuery(form, "data-company-filter", ["q", "country", "sector"]);
        focusHash("company");
      };
      form.addEventListener("input", render);
      form.addEventListener("change", render);
      $("[data-company-filter-reset]", form)?.addEventListener("click", () => {
        form.reset();
        render();
        $('[data-company-filter="q"]', form)?.focus();
      });
      addEventListener("hashchange", () => focusHash("company"));
      render();
    } catch (error) {
      console.error("Unable to initialize company directory:", error);
      list.innerHTML = emptyState("The company directory is unavailable", "The local dataset could not be loaded. When previewing locally, use a web server.", "data/companies.json");
      list.setAttribute("aria-busy", "false");
      setText("[data-company-result-count]", "Unavailable");
      setStatus("Data unavailable", "error");
      $$("input, select, button", form).forEach((control) => { control.disabled = true; });
    }
  }

  function normalizeNotFoundLinks() {
    if (page !== "404") return;
    $$('a[href]:not([href^="#"]):not([href^="http"]):not([href^="mailto:"])').forEach((anchor) => {
      anchor.href = local(anchor.getAttribute("href"));
    });
  }

  initNavigation();
  normalizeNotFoundLinks();
  if (page === "events") initEvents();
  if (page === "companies") initCompanies();
})();
