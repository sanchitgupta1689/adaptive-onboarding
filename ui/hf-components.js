/**
 * @healthfirst/ui — Web Components v1.0
 *
 * Drop-in component library for HealthFirst embedded apps.
 * All components consume --hf-* CSS custom properties automatically,
 * so they theme-switch live when the platform sends THEME_CHANGE.
 *
 * Usage:
 *   <script src="/ui/hf-components.js"></script>
 *
 *   <hf-button variant="primary">Buy Now</hf-button>
 *   <hf-card elevation="1">...</hf-card>
 *   <hf-badge color="success">Recommended</hf-badge>
 *   <hf-input label="Email" type="email"></hf-input>
 *   <hf-spinner></hf-spinner>
 *   <hf-avatar initials="PK"></hf-avatar>
 *   <hf-divider></hf-divider>
 */

// ─── Shared token bridge ──────────────────────────────────────────────────────
// CSS custom properties cascade into open shadow DOM, so --hf-* vars set on
// :root by the SDK are automatically available inside every component.

const BASE_STYLES = `
  :host { box-sizing: border-box; }
  *, *::before, *::after { box-sizing: inherit; }
`;

// ─── hf-button ────────────────────────────────────────────────────────────────
// Attributes: variant (primary|secondary|ghost|danger), size (sm|md|lg),
//             disabled, loading, full-width
class HfButton extends HTMLElement {
  static get observedAttributes() {
    return ['variant', 'size', 'disabled', 'loading', 'full-width'];
  }

  connectedCallback()                { this._render(); }
  attributeChangedCallback()         { this._render(); }

  _render() {
    const variant   = this.getAttribute('variant')   || 'primary';
    const size      = this.getAttribute('size')      || 'md';
    const disabled  = this.hasAttribute('disabled');
    const loading   = this.hasAttribute('loading');
    const fullWidth = this.hasAttribute('full-width');

    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });

    this.shadowRoot.innerHTML = `
      <style>
        ${BASE_STYLES}
        :host { display: inline-block; }
        :host([full-width]) { display: block; }

        button {
          display:       inline-flex;
          align-items:   center;
          justify-content: center;
          gap:           8px;
          border:        none;
          cursor:        pointer;
          font-family:   var(--hf-font-family, Inter, sans-serif);
          font-weight:   600;
          border-radius: var(--hf-radius-md, 12px);
          transition:    opacity .15s, transform .1s, background .2s;
          width:         ${fullWidth ? '100%' : 'auto'};
          letter-spacing: .2px;
        }
        button:active:not(:disabled) { transform: scale(.98); }
        button:disabled              { opacity: .45; cursor: not-allowed; }

        /* Sizes */
        button.sm { padding: 7px 14px;  font-size: 12px; }
        button.md { padding: 11px 20px; font-size: 14px; }
        button.lg { padding: 14px 28px; font-size: 16px; }

        /* Variants */
        button.primary {
          background: var(--hf-color-primary, #1A7F5A);
          color: #fff;
        }
        button.primary:hover:not(:disabled) { opacity: .88; }

        button.secondary {
          background: transparent;
          color: var(--hf-color-primary, #1A7F5A);
          border: 1.5px solid var(--hf-color-primary, #1A7F5A);
        }
        button.secondary:hover:not(:disabled) { background: rgba(26,127,90,.08); }

        button.ghost {
          background: var(--hf-color-surface, #fff);
          color: var(--hf-color-text, #1A1A1A);
          border: 1px solid rgba(0,0,0,.12);
        }
        button.ghost:hover:not(:disabled) { background: rgba(0,0,0,.04); }

        button.danger {
          background: var(--hf-color-error, #DC2626);
          color: #fff;
        }
        button.danger:hover:not(:disabled) { opacity: .88; }

        /* Spinner inside button */
        .spin {
          width: 14px; height: 14px;
          border: 2px solid rgba(255,255,255,.3);
          border-top-color: #fff;
          border-radius: 50%;
          animation: spin .7s linear infinite;
        }
        .spin.dark {
          border-color: rgba(0,0,0,.15);
          border-top-color: var(--hf-color-primary, #1A7F5A);
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      </style>
      <button class="${variant} ${size}" ${disabled || loading ? 'disabled' : ''}>
        ${loading ? `<span class="spin ${variant === 'ghost' || variant === 'secondary' ? 'dark' : ''}"></span>` : ''}
        <slot></slot>
      </button>`;

    // Forward clicks from shadow button
    const btn = this.shadowRoot.querySelector('button');
    btn.addEventListener('click', e => {
      if (!disabled && !loading)
        this.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
      e.stopPropagation();
    });
  }
}

// ─── hf-card ──────────────────────────────────────────────────────────────────
// Attributes: elevation (0|1|2), padding (sm|md|lg|none)
class HfCard extends HTMLElement {
  static get observedAttributes() { return ['elevation', 'padding']; }
  connectedCallback()              { this._render(); }
  attributeChangedCallback()       { this._render(); }

  _render() {
    const elevation = this.getAttribute('elevation') || '1';
    const padding   = this.getAttribute('padding')   || 'md';

    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });

    const shadows = {
      '0': 'none',
      '1': '0 1px 3px rgba(0,0,0,.07), 0 6px 18px rgba(0,0,0,.04)',
      '2': '0 4px 12px rgba(0,0,0,.1),  0 16px 40px rgba(0,0,0,.08)',
    };
    const pads = { none:'0', sm:'12px', md:'20px', lg:'28px' };

    this.shadowRoot.innerHTML = `
      <style>
        ${BASE_STYLES}
        :host { display: block; }
        .card {
          background:    var(--hf-color-surface, #fff);
          border-radius: var(--hf-radius-lg, 20px);
          border:        1px solid rgba(0,0,0,.06);
          box-shadow:    ${shadows[elevation] || shadows['1']};
          padding:       ${pads[padding] || pads['md']};
          transition:    background .3s, box-shadow .3s;
        }
      </style>
      <div class="card"><slot></slot></div>`;
  }
}

// ─── hf-badge ─────────────────────────────────────────────────────────────────
// Attributes: color (primary|success|error|muted|warning)
class HfBadge extends HTMLElement {
  static get observedAttributes() { return ['color']; }
  connectedCallback()              { this._render(); }
  attributeChangedCallback()       { this._render(); }

  _render() {
    const color = this.getAttribute('color') || 'primary';
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });

    const schemes = {
      primary: 'background:rgba(26,127,90,.12); color:var(--hf-color-primary,#1A7F5A); border-color:rgba(26,127,90,.2)',
      success: 'background:rgba(22,163,74,.12); color:var(--hf-color-success,#16A34A); border-color:rgba(22,163,74,.2)',
      error:   'background:rgba(220,38,38,.1);  color:var(--hf-color-error,#DC2626);   border-color:rgba(220,38,38,.2)',
      muted:   'background:rgba(107,114,128,.1);color:var(--hf-color-muted,#6B7280);   border-color:rgba(107,114,128,.2)',
      warning: 'background:rgba(217,119,6,.1);  color:#D97706;                          border-color:rgba(217,119,6,.2)',
    };

    this.shadowRoot.innerHTML = `
      <style>
        ${BASE_STYLES}
        :host { display: inline-block; }
        span {
          display:        inline-block;
          font-family:    var(--hf-font-family, Inter, sans-serif);
          font-size:      11px;
          font-weight:    600;
          letter-spacing: .4px;
          text-transform: capitalize;
          padding:        3px 10px;
          border-radius:  20px;
          border:         1px solid transparent;
          ${schemes[color] || schemes['primary']}
        }
      </style>
      <span><slot></slot></span>`;
  }
}

// ─── hf-input ─────────────────────────────────────────────────────────────────
// Attributes: label, type, placeholder, value, error, disabled, required, name
class HfInput extends HTMLElement {
  static get observedAttributes() {
    return ['label', 'type', 'placeholder', 'value', 'error', 'disabled', 'required', 'name'];
  }
  connectedCallback()        { this._render(); }
  attributeChangedCallback() { this._render(); }

  get value() { return this.shadowRoot?.querySelector('input')?.value ?? ''; }

  _render() {
    const label       = this.getAttribute('label')       || '';
    const type        = this.getAttribute('type')        || 'text';
    const placeholder = this.getAttribute('placeholder') || '';
    const value       = this.getAttribute('value')       || '';
    const error       = this.getAttribute('error')       || '';
    const disabled    = this.hasAttribute('disabled');
    const required    = this.hasAttribute('required');
    const name        = this.getAttribute('name')        || '';

    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });

    this.shadowRoot.innerHTML = `
      <style>
        ${BASE_STYLES}
        :host { display: block; }
        .wrap { display: flex; flex-direction: column; gap: 5px; }
        label {
          font-family:  var(--hf-font-family, Inter, sans-serif);
          font-size:    12px;
          font-weight:  600;
          color:        var(--hf-color-muted, #6B7280);
          letter-spacing: .3px;
        }
        input {
          font-family:    var(--hf-font-family, Inter, sans-serif);
          font-size:      14px;
          color:          var(--hf-color-text, #1A1A1A);
          background:     var(--hf-color-surface, #fff);
          border:         1.5px solid ${error ? 'var(--hf-color-error,#DC2626)' : 'rgba(0,0,0,.15)'};
          border-radius:  var(--hf-radius-sm, 6px);
          padding:        9px 12px;
          width:          100%;
          outline:        none;
          transition:     border-color .15s;
        }
        input:focus { border-color: ${error ? 'var(--hf-color-error,#DC2626)' : 'var(--hf-color-primary,#1A7F5A)'}; }
        input:disabled { opacity: .5; cursor: not-allowed; }
        input::placeholder { color: var(--hf-color-muted, #6B7280); }
        .error-msg {
          font-family: var(--hf-font-family, Inter, sans-serif);
          font-size: 12px;
          color: var(--hf-color-error, #DC2626);
        }
      </style>
      <div class="wrap">
        ${label ? `<label>${label}${required ? ' *' : ''}</label>` : ''}
        <input type="${type}" placeholder="${placeholder}" value="${value}"
               name="${name}" ${disabled ? 'disabled' : ''} ${required ? 'required' : ''}>
        ${error ? `<span class="error-msg">${error}</span>` : ''}
      </div>`;

    // Forward input/change events
    this.shadowRoot.querySelector('input').addEventListener('input', e => {
      this.dispatchEvent(new CustomEvent('input', { detail: e.target.value, bubbles: true, composed: true }));
    });
    this.shadowRoot.querySelector('input').addEventListener('change', e => {
      this.dispatchEvent(new CustomEvent('change', { detail: e.target.value, bubbles: true, composed: true }));
    });
  }
}

// ─── hf-spinner ───────────────────────────────────────────────────────────────
// Attributes: size (sm|md|lg), color (primary|muted|white)
class HfSpinner extends HTMLElement {
  static get observedAttributes() { return ['size', 'color']; }
  connectedCallback()              { this._render(); }
  attributeChangedCallback()       { this._render(); }

  _render() {
    const size  = this.getAttribute('size')  || 'md';
    const color = this.getAttribute('color') || 'primary';
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });

    const sizes = { sm: '16px', md: '24px', lg: '36px' };
    const colors = {
      primary: 'var(--hf-color-primary, #1A7F5A)',
      muted:   'var(--hf-color-muted, #6B7280)',
      white:   '#fff',
    };
    const s = sizes[size] || sizes['md'];
    const c = colors[color] || colors['primary'];

    this.shadowRoot.innerHTML = `
      <style>
        ${BASE_STYLES}
        :host { display: inline-flex; align-items: center; justify-content: center; }
        .ring {
          width: ${s}; height: ${s};
          border: 2.5px solid rgba(0,0,0,.1);
          border-top-color: ${c};
          border-radius: 50%;
          animation: spin .75s linear infinite;
          flex-shrink: 0;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      </style>
      <div class="ring"></div>`;
  }
}

// ─── hf-avatar ────────────────────────────────────────────────────────────────
// Attributes: initials, src, size (sm|md|lg)
class HfAvatar extends HTMLElement {
  static get observedAttributes() { return ['initials', 'src', 'size']; }
  connectedCallback()              { this._render(); }
  attributeChangedCallback()       { this._render(); }

  _render() {
    const initials = (this.getAttribute('initials') || '?').slice(0, 2).toUpperCase();
    const src      = this.getAttribute('src')  || '';
    const size     = this.getAttribute('size') || 'md';
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });

    const sizes = { sm: '28px', md: '40px', lg: '56px' };
    const fonts = { sm: '11px', md: '14px', lg: '20px' };
    const s = sizes[size] || sizes['md'];
    const f = fonts[size] || fonts['md'];

    this.shadowRoot.innerHTML = `
      <style>
        ${BASE_STYLES}
        :host { display: inline-block; }
        .av {
          width: ${s}; height: ${s};
          border-radius: 50%;
          background: linear-gradient(135deg, var(--hf-color-primary,#1A7F5A) 0%,
                                              rgba(26,127,90,.55) 100%);
          color: #fff;
          font-family:  var(--hf-font-family, Inter, sans-serif);
          font-size:    ${f};
          font-weight:  700;
          display:      flex; align-items: center; justify-content: center;
          overflow:     hidden; flex-shrink: 0;
          user-select:  none;
        }
        img { width: 100%; height: 100%; object-fit: cover; }
      </style>
      <div class="av">
        ${src ? `<img src="${src}" alt="${initials}">` : initials}
      </div>`;
  }
}

// ─── hf-divider ───────────────────────────────────────────────────────────────
// Attributes: label
class HfDivider extends HTMLElement {
  static get observedAttributes() { return ['label']; }
  connectedCallback()              { this._render(); }
  attributeChangedCallback()       { this._render(); }

  _render() {
    const label = this.getAttribute('label') || '';
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });

    this.shadowRoot.innerHTML = `
      <style>
        ${BASE_STYLES}
        :host { display: block; }
        .line {
          display: flex; align-items: center; gap: 12px;
          color:      var(--hf-color-muted, #6B7280);
          font-family: var(--hf-font-family, Inter, sans-serif);
          font-size:  12px;
        }
        .line::before, .line::after {
          content: ''; flex: 1;
          border-top: 1px solid rgba(0,0,0,.1);
        }
      </style>
      <div class="line">${label ? `<span>${label}</span>` : ''}</div>`;
  }
}

// ─── Register all components ──────────────────────────────────────────────────
customElements.define('hf-button',  HfButton);
customElements.define('hf-card',    HfCard);
customElements.define('hf-badge',   HfBadge);
customElements.define('hf-input',   HfInput);
customElements.define('hf-spinner', HfSpinner);
customElements.define('hf-avatar',  HfAvatar);
customElements.define('hf-divider', HfDivider);
