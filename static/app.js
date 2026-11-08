(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  /* ---------- sidebar ---------- */
  const setSidebar = (open) => {
    const sidebar = $('#sidebar');
    document.body.classList.toggle('sidebar-open', open);
    if (sidebar) sidebar.classList.toggle('is-open', open);
  };

  document.addEventListener('click', (event) => {
    if (event.target.closest('[data-sidebar-open]')) setSidebar(true);
    if (event.target.closest('[data-sidebar-close]')) setSidebar(false);
    if (event.target.closest('.nav-item') && window.matchMedia('(max-width: 1020px)').matches) {
      setSidebar(false);
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setSidebar(false);
  });

  /* ---------- flash messages ---------- */
  $$('.flash').forEach((flash) => {
    const close = $('.flash-close', flash);
    if (close) close.addEventListener('click', () => flash.remove());
    if (flash.classList.contains('flash--success') || flash.classList.contains('flash--info')) {
      window.setTimeout(() => flash.remove(), 6500);
    }
  });

  /* ---------- tabs ---------- */
  const activateTab = (group, name) => {
    const tabs = $$('[data-tab]', group);
    if (!tabs.some((tab) => tab.dataset.tab === name)) return;
    tabs.forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    $$('[data-tab-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.tabPanel !== name;
    });
  };

  $$('[data-tabs]').forEach((group) => {
    const tabs = $$('[data-tab]', group);
    if (!tabs.length) return;
    group.setAttribute('role', 'tablist');
    const initial = tabs.find((tab) => tab.classList.contains('is-active')) || tabs[0];
    activateTab(group, initial.dataset.tab);
    group.addEventListener('click', (event) => {
      const tab = event.target.closest('[data-tab]');
      if (tab && group.contains(tab)) activateTab(group, tab.dataset.tab);
    });
  });

  if (window.location.hash === '#import') {
    const group = $('[data-tabs]');
    if (group) activateTab(group, 'import-url');
  }

  /* ---------- file inputs ---------- */
  $$('[data-file-input]').forEach((input) => {
    input.addEventListener('change', () => {
      const form = input.closest('form');
      const label = form && $('[data-file-name]', form);
      if (!label) return;
      const file = input.files && input.files[0];
      label.textContent = file ? `${file.name} · ${formatSize(file.size)}` : '';
      label.classList.toggle('is-filled', Boolean(file));
    });
  });

  const formatSize = (bytes) => {
    if (!bytes) return '۰ بایت';
    const units = ['بایت', 'کیلوبایت', 'مگابایت', 'گیگابایت'];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const value = bytes / Math.pow(1024, index);
    return `${value.toLocaleString('fa-IR', { maximumFractionDigits: 1 })} ${units[index]}`;
  };

  /* ---------- repeaters (experience / education) ---------- */
  const buildRepeater = (config, root) => {
    if (!root) return;
    const list = $('[data-list]', root);
    const empty = $('[data-empty]', root);
    const addButton = $('[data-add]', root);
    const template = document.getElementById(config.template);
    const target = document.getElementById(config.target);
    if (!list || !template) return;

    const rows = [];

    const sync = () => {
      const values = rows.map((row) => row.value).filter((item) => {
        return Object.values(item).some((value) => {
          if (Array.isArray(value)) return value.length > 0;
          return String(value || '').trim() !== '';
        });
      });
      if (target) target.value = JSON.stringify(values);
      if (empty) empty.style.display = rows.length ? 'none' : '';
    };

    const refreshTitle = () => {
      rows.forEach((row, index) => {
        const heading = row.el.querySelector('[data-title]');
        if (!heading) return;
        const primary = row.value.title || row.value.degree || '';
        heading.textContent = primary.trim() || `${config.title} ${toFa(index + 1)}`;
      });
    };

    const readRow = (row) => {
      $$('[data-k]', row.el).forEach((input) => {
        const key = input.dataset.k;
        if (key === 'bullets') {
          row.value.bullets = input.value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
        } else {
          row.value[key] = input.value.trim();
        }
      });
      refreshTitle();
      sync();
    };

    const createRow = (data = {}) => {
      const fragment = template.content.cloneNode(true);
      const el = fragment.firstElementChild;
      const value = {};
      $$('[data-k]', el).forEach((input) => {
        const key = input.dataset.k;
        const raw = data[key];
        if (key === 'bullets') {
          const bullets = Array.isArray(raw) ? raw : [];
          input.value = bullets.join('\n');
          value.bullets = bullets.slice();
        } else {
          input.value = raw == null ? '' : String(raw);
          value[key] = input.value;
        }
        input.addEventListener('input', () => readRow(row));
      });
      const row = { el, value };
      const remove = $('[data-remove]', el);
      if (remove) {
        remove.addEventListener('click', () => {
          const index = rows.indexOf(row);
          if (index !== -1) rows.splice(index, 1);
          el.remove();
          refreshTitle();
          sync();
        });
      }
      list.appendChild(el);
      rows.push(row);
      return row;
    };

    (Array.isArray(config.data) ? config.data : []).forEach((data) => createRow(data || {}));
    refreshTitle();
    sync();

    if (addButton) {
      addButton.addEventListener('click', () => {
        const row = createRow({});
        const first = $('[data-k]', row.el);
        if (first) first.focus();
        refreshTitle();
        sync();
        row.el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      });
    }
  };

  const toFa = (value) => String(value).replace(/\d/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[Number(digit)]);

  if (window.RESUMEYAR_REPEATERS) {
    Object.entries(window.RESUMEYAR_REPEATERS).forEach(([key, config]) => {
      buildRepeater(config, $(`[data-repeater="${key}"]`));
    });
  }

  /* ---------- confirmations & busy overlay ---------- */
  const busy = $('#busy');
  const showBusy = () => {
    if (busy) busy.hidden = false;
    document.documentElement.classList.add('is-busy');
  };
  const hideBusy = () => {
    if (busy) busy.hidden = true;
    document.documentElement.classList.remove('is-busy');
  };

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const submitter = event.submitter;
    if (submitter && submitter.hasAttribute('data-skip-confirm')) {
      if (submitter.hasAttribute('data-skip-busy')) return;
    }
    const message = form.dataset.confirm || (submitter && submitter.dataset.confirm);
    if (message && !window.confirm(message)) {
      event.preventDefault();
      return;
    }
    if (form.hasAttribute('data-busy') && !(submitter && submitter.hasAttribute('data-skip-busy'))) {
      showBusy();
    }
  });

  window.addEventListener('pageshow', hideBusy);

  /* ---------- fetch job details from a link ---------- */
  const extractButton = $('[data-extract-job]');
  if (extractButton) {
    const form = extractButton.closest('form');
    const status = $('[data-extract-status]', form || document);
    const meta = $('meta[name="csrf-token"]');
    const csrf = meta ? meta.getAttribute('content') : '';

    const fields = {
      title: $('#job-title'),
      company: $('#job-company'),
      location: $('#job-location'),
      contact_email: $('#job-contact'),
      description: $('#job-description'),
    };

    const setStatus = (message, kind = '') => {
      if (!status) return;
      status.textContent = message || '';
      status.classList.toggle('is-error', kind === 'error');
      status.classList.toggle('is-ok', kind === 'ok');
    };

    const fill = (field, value) => {
      if (!field || !value) return false;
      if (field.value.trim()) return false;
      field.value = value;
      return true;
    };

    extractButton.addEventListener('click', async () => {
      const urlInput = $('#job-url');
      const url = urlInput ? urlInput.value.trim() : '';
      if (!url) {
        setStatus('ابتدا لینک آگهی را وارد کنید.', 'error');
        if (urlInput) urlInput.focus();
        return;
      }

      const original = extractButton.innerHTML;
      extractButton.disabled = true;
      extractButton.textContent = 'در حال خواندن لینک…';
      setStatus('صفحه آگهی در حال بررسی است…');

      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), 35000);

      try {
        const response = await fetch('/api/fetch-job', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrf,
          },
          body: JSON.stringify({ url }),
          signal: controller.signal,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.error || 'خواندن این لینک ممکن نشد.');
        }

        let filled = 0;
        Object.entries(fields).forEach(([key, field]) => {
          if (fill(field, data[key])) filled += 1;
        });
        if (urlInput && data.url && !urlInput.value) urlInput.value = data.url;

        const language = $('#job-language');
        if (language && data.language && ['fa', 'en'].includes(data.language) && language.value === 'auto') {
          language.value = data.language;
        }

        if (filled) {
          setStatus('اطلاعات از لینک خوانده شد. پیش از ذخیره، متن و عنوان را بازبینی کنید.', 'ok');
        } else {
          setStatus('اطلاعات صفحه خوانده شد، اما فیلدها از قبل پر بودند. متن آگهی را کنترل کنید.', 'ok');
        }
      } catch (error) {
        const message = error.name === 'AbortError'
          ? 'زمان خواندن لینک طولانی شد. متن آگهی را دستی وارد کنید.'
          : (error.message || 'خواندن لینک ناموفق بود.');
        setStatus(message, 'error');
      } finally {
        window.clearTimeout(timer);
        extractButton.disabled = false;
        extractButton.innerHTML = original;
      }
    });
  }

  /* ---------- copy buttons ---------- */
  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-copy-target]');
    if (!button || button.dataset.copyBusy) return;
    event.preventDefault();
    const input = document.getElementById(button.dataset.copyTarget);
    if (!input) return;
    const text = input.value != null ? input.value : (input.textContent || '');
    button.dataset.copyBusy = '1';
    const original = button.textContent;
    const finish = (label) => {
      button.textContent = label;
      window.setTimeout(() => {
        button.textContent = original;
        delete button.dataset.copyBusy;
      }, 1800);
    };

    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const helper = document.createElement('textarea');
        helper.value = text;
        helper.setAttribute('readonly', '');
        helper.style.position = 'fixed';
        helper.style.opacity = '0';
        document.body.appendChild(helper);
        helper.select();
        document.execCommand('copy');
        helper.remove();
      }
      finish('کپی شد');
    } catch (error) {
      finish('کپی نشد');
    }
  });
})();
