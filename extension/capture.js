/* Read-only, isolated-world DOM adapter. No page globals, cookies, network, or hidden dictionaries. */
(() => {
  const VERSION = 'tesla-cn-modely-dom/0.1.1';
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  const visible = el => !!el && !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none';
  const text = el => clean(el?.innerText || el?.textContent);
  const money = raw => {
    const m = String(raw).match(/[¥￥]\s*([\d,]+(?:\.\d{1,2})?)/);
    return m ? Math.round(Number(m[1].replaceAll(',', '')) * 100) : null;
  };
  const all = (root, selector) => root ? [...root.querySelectorAll(selector)] : [];
  function project() {
    const main = document.querySelector('#main-content');
    const footer = [...document.querySelectorAll('.aside-footer--container')].find(visible);
    const dialog = [...document.querySelectorAll('dialog[open], #tds-main-modal[open]')].find(visible);
    const selected = all(main, 'input:checked').map(input => {
      const label = [...(input.labels || [])].find(visible);
      // Tesla visually hides radio inputs, so associated visible labels are the evidence.
      return label ? { name: input.name, id: input.id, value: input.value, label: text(label), aria: clean(input.getAttribute('aria-label') || label.getAttribute('aria-label')), data_id: label.getAttribute('data-id') } : null;
    }).filter(Boolean);
    const fin = dialog?.querySelector('#finance_options-loan-panel');
    const finance = fin && visible(fin) ? {
      text: text(fin).slice(0, 9000),
      inputs: all(fin, 'input,select').filter(visible).map(el => ({ id: el.id, name: el.name, value: el.tagName === 'SELECT' ? clean(el.selectedOptions?.[0]?.textContent) : el.value, label: clean([...(el.labels || [])].map(text).join(' ')), type: el.type })),
    } : null;
    // Whitelisted current configurator text only; never serializes HTML or JS objects.
    const groups = all(main, '[class*="group-"]').filter(visible).map(el => ({ class_name: el.className, text: text(el).slice(0, 1000) })).filter(x => /COMBINED_TRIMS|PAINT|WHEELS|INTERIOR|PREMIUM_PACKAGE|SEAT|AUTOPILOT|ACCESSOR/i.test(x.class_name)).slice(0, 24);
    const checkboxes = all(main, 'input[type="checkbox"]').map(input => {
      const label = [...(input.labels || [])].find(visible);
      if (!label) return null;
      const ancestors = []; let parent = input.parentElement;
      for (let i = 0; parent && parent !== main && i < 5; i++, parent = parent.parentElement) {
        ancestors.push({tag: parent.tagName, class_name: parent.className, headings: all(parent, 'h2,h3,h4,legend').filter(visible).map(text), text: text(parent).slice(0, 600)});
      }
      return {name: input.name, id: input.id, checked: input.checked, label: text(label), aria: clean(input.getAttribute('aria-label')), ancestors};
    }).filter(Boolean);
    // Explicit DOM sections verified on the live site. Connectivity subscriptions are excluded.
    const accessorySections = all(main, '#RECOMMENDED_ACCESSORIES, #CHARGING_ACCESSORIES').filter(visible);
    const accessories = accessorySections.length ? {
      heading: '配件', selector: '#RECOMMENDED_ACCESSORIES, #CHARGING_ACCESSORIES',
      sections: accessorySections.map(el => ({ id: el.id, text: text(el).slice(0, 1600), control_count: all(el, 'input[type="checkbox"]').length })),
      options: accessorySections.flatMap(el => all(el, 'input[type="checkbox"]').map(input => {
        const label = [...(input.labels || [])].find(visible);
        return label ? {label: text(label), checked: input.checked} : null;
      })),
    } : null;
    const mainText = text(main);
    return {
      selected, footer: text(footer).slice(0, 5000), finance, groups, checkboxes, accessories,
      parameter_lines: mainText.match(/.{0,45}(?:CLTC|km\/h|公里|续航|加速|交付|km|秒).{0,65}/g)?.slice(0, 16) || [],
      busy: all(main, '[aria-busy="true"], [role="progressbar"]').some(visible),
      has_main: !!main,
    };
  }
  const digest = async value => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(value))))].map(x => x.toString(16).padStart(2, '0')).join('');
  function parse(projection, observedAt) {
    const fields = [], issues = [];
    const add = (key, value, raw, selector, unit = null, kind = 'dom_text') => {
      if (value !== null && value !== undefined && value !== '') fields.push({ key, value, unit, raw_text: raw, evidence: { kind, selector_hint: selector }, observed_at: observedAt });
    };
    const chosen = projection.selected;
    const trim = chosen.find(x => x.name === 'trim-category-COMBINED_TRIMS');
    if (trim) {
      add('model', 'Model Y', trim.label, '.group-COMBINED_TRIMS input:checked + label', null, 'dom_selected');
      add('variant', trim.label.replace(/[¥￥].*$/, '').trim(), trim.label, 'input[name="trim-category-COMBINED_TRIMS"]:checked labels', null, 'dom_selected');
    }
    const classify = (key, pattern) => {
      const match = chosen.find(x => pattern.test(`${x.name} ${x.id} ${x.data_id} ${x.aria} ${x.label}`) && x !== trim);
      if (match) add(key, match.aria || match.label, match.label || match.aria, `input:checked[name="${match.name}"] labels`, null, 'dom_selected');
    };
    classify('paint', /PAINT|车漆|珍珠白|星空灰|纯黑|快银|烈焰红|冰河蓝/i);
    classify('wheels', /WHEELS|轮毂/i);
    classify('interior', /INTERIOR|PREMIUM_PACKAGE|内饰/i);
    classify('seats', /SEAT|五座|七座|六座/i);
    classify('autopilot', /AUTOPILOT|辅助驾驶|智能辅助/i);
    if (!fields.some(x => x.key === 'seats')) {
      const seatGroup = projection.groups.find(x => /group-REAR_SEATS/.test(x.class_name));
      const seat = seatGroup?.text.match(/五座|七座|六座/);
      if (seat && /group--selected_/.test(seatGroup.class_name)) add('seats', seat[0], seatGroup.text, '.group-REAR_SEATS[class*=group--selected_]', null, 'dom_selected');
    }
    if (projection.accessories?.options?.length && projection.accessories.options.every(Boolean)) {
      const options = projection.accessories.options;
      add('accessories', options.filter(x => x.checked).map(x => x.label), options.map(x => `${x.label}: ${x.checked ? '已选' : '未选'}`).join('; '), projection.accessories.selector, null, 'dom_selected');
    }
    const footer = projection.footer;
    // Anchor the total to the price label. A loan footer may start with the monthly payment.
    const priceMatch = footer.match(/(?:车辆价格|车价|现金价格|购买价格|总价)[：:\s]*([¥￥]\s*[\d,]+(?:\.\d{1,2})?)/) || footer.match(/([¥￥]\s*[\d,]+(?:\.\d{1,2})?)\s*(?:车辆价格|车价|现金价格|购买价格|总价)/);
    if (priceMatch) {
      add('vehicle_price', money(priceMatch[1]), priceMatch[0], '.aside-footer--container', 'CNY_fen');
      add('price_basis', '当前页面标明的车辆价格', priceMatch[0], '.aside-footer--container');
    } else if ((footer.match(/[¥￥]\s*[\d,]+/g) || []).length === 1 && !/月供|每月|\/月/.test(footer)) {
      add('vehicle_price', money(footer), footer, '.aside-footer--container', 'CNY_fen');
      add('price_basis', '配置器底部单一车辆价格；需销售核对', footer, '.aside-footer--container');
    }
    const facts = projection.parameter_lines.join(' ');
    const range = facts.match(/(\d{3})\s*(?:公里|km)\s*(?:续航|CLTC)/i) || facts.match(/(?:续航|CLTC)[^\d]{0,25}(\d{3})\s*(?:公里|km)/i);
    if (range) add('range_cltc', Number(range[1]), range[0], '#main-content visible text', 'km');
    const speed = facts.match(/(\d{3})\s*(?:km\/h|公里\/小时)/i);
    if (speed) add('top_speed', Number(speed[1]), speed[0], '#main-content visible text', 'km/h');
    const accel = facts.match(/(\d(?:\.\d)?)\s*(?:秒|s)\s*(?:百公里|0[-–]100|加速)/i);
    if (accel) add('zero_to_hundred', Number(accel[1]), accel[0], '#main-content visible text', 's');
    const delivery = facts.match(/(?:预计交付|交付)[：:\s]*[^。]{0,35}/);
    if (delivery) add('delivery', delivery[0], delivery[0], '#main-content visible text');
    const finance = projection.finance;
    if (finance) {
      const down = finance.inputs.find(x => x.id === 'downPaymentAmountInput');
      if (down) add('down_payment', money(down.value), `${down.label} ${down.value}`, '#downPaymentAmountInput', 'CNY_fen');
      const product = finance.inputs.find(x => /贷款|金融|融资/.test(x.value) && x.type?.startsWith('select'));
      if (product) add('finance_product', product.value, product.value, '#finance_options-loan-panel select');
      const patterns = [
        ['principal', /(?:贷款金额|融资金额|贷款本金)[：:\s]*([¥￥]\s*[\d,]+(?:\.\d{1,2})?)/, 'CNY_fen'],
        ['monthly_payment', /(?:月供|每月还款)[：:\s]*([¥￥]\s*[\d,]+(?:\.\d{1,2})?)/, 'CNY_fen'],
        ['term_months', /(?:期数\s*)?(\d+)\s*个月/, 'month'],
      ];
      for (const [key, pattern, unit] of patterns) {
        const match = finance.text.match(pattern);
        if (match) add(key, unit === 'CNY_fen' ? money(match[1]) : Number(match[1]), match[0], '#finance_options-loan-panel', unit);
      }
      if (!fields.some(x => x.key === 'monthly_payment')) {
        const monthly = finance.text.match(/([¥￥]\s*[\d,]+(?:\.\d{1,2})?)\s*\/\s*月/);
        if (monthly) add('monthly_payment', money(monthly[1]), monthly[0], '#finance_options-loan-panel', 'CNY_fen');
      }
      // Basis and value must be taken from the SAME occurrence; fee rate is not APR.
      const rate = finance.text.match(/(年化费率|折合年化利率|年利率|年化利率)[：:\s%]*(\d+(?:\.\d+)?)\s*%/);
      if (rate) {
        add('rate_value', Number(rate[2]), rate[0], '#finance_options-loan-panel', 'percent');
        add('rate_basis', rate[1], rate[0], '#finance_options-loan-panel');
      }
    } else issues.push({ code: 'FINANCE_NOT_VISIBLE', severity: 'warning', message: '金融面板未展开；金融字段保持缺失。展开贷款面板后可重新 Capture。' });
    const required = ['model', 'variant', 'paint', 'wheels', 'interior', 'seats', 'autopilot', 'accessories', 'vehicle_price', 'price_basis'];
    for (const key of required) if (!fields.some(x => x.key === key)) issues.push({ code: 'FIELD_MISSING', field: key, severity: 'warning', message: `${key} 尚无明确当前页面证据，快照不完整。` });
    const val = key => fields.find(x => x.key === key)?.value;
    if ([val('vehicle_price'), val('down_payment'), val('principal')].every(x => typeof x === 'number') && val('vehicle_price') !== val('down_payment') + val('principal')) issues.push({ code: 'FINANCE_PRICE_CONFLICT', severity: 'error', message: '车辆价格不等于首付加贷款本金；缺少可解释费用/优惠，不可作为完整金融方案。' });
    return { fields, issues };
  }
  async function capture() {
    const url = new URL(location.href);
    if (url.protocol !== 'https:' || url.hostname !== 'www.tesla.cn' || url.pathname !== '/modely/design' || window.top !== window) throw new Error('不支持的网页，仅允许 Tesla 中国 Model Y 顶层页面。');
    const first = project();
    // Two projections separated by the agreed 500 ms stability window.
    await new Promise(resolve => setTimeout(resolve, 500));
    const second = project(), observedAt = new Date().toISOString();
    const firstHash = await digest(first), secondHash = await digest(second);
    const unstable = firstHash !== secondHash || second.busy || !second.has_main;
    const parsed = parse(second, observedAt);
    if (unstable) parsed.issues.unshift({ code: 'PAGE_UNSTABLE', severity: 'error', message: '页面正在更新或尚未就绪，请等待完成后重新 Capture。本次不保存候选。' });
    return { source_url: location.href, captured_at: observedAt, adapter_version: VERSION, page_fingerprint: secondHash, readiness: unstable ? 'unstable' : 'ready', completeness: parsed.issues.some(x => x.code === 'FIELD_MISSING' || x.severity === 'error') ? 'incomplete' : 'complete', ...parsed, diagnostics: { stable_window_ms: 500, first_fingerprint: firstHash, second_fingerprint: secondHash, ...second } };
  }
  globalThis.TessCapture = { capture, parse, money };
})();
