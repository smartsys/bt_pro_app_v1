/**
 * CandleChart — wiederverwendbarer OHLC-Candle-Chart (lightweight-charts v5).
 *
 * Erzeugt Toolbar und Chart komplett selbst in einem uebergebenen Wurzel-Element.
 * Bedienelemente: Zeitrahmen-Buttons (visuelles Resampling nach oben), Sprung an
 * Anfang/Ende, Fit, Charthoehe (400/560, persistiert) und Lineal (Preis-Differenz).
 *
 * Voraussetzung: lightweight-charts (standalone) ist global als LightweightCharts geladen.
 *
 * Verwendung:
 *   CandleChart.mount(document.getElementById('chart-root'), {
 *     symbol: 'BTC/USDT', exchange: 'binance', timeframe: '1h',
 *     start: '2023-01-01', end: '2024-01-01', storageKey: 'analyse-chart',
 *   });
 */
(function (window, document) {
  'use strict';

  var TF_SEC = {
    '1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '2h': 7200,
    '4h': 14400, '6h': 21600, '12h': 43200, '1d': 86400, '1w': 604800,
  };
  var TF_LIST = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '1w'];

  var HEIGHT_NORMAL = 400;
  var HEIGHT_TALL = 560;

  /**
   * Candles auf ein groeberes Raster aggregieren (first-open / max-high / min-low / last-close).
   * Bucket-Grenze ist das UTC-Epoch-Raster von targetSec.
   */
  function resampleCandles(candles, targetSec) {
    var result = [];
    var group = [];
    var bucket = null;
    function flush() {
      if (!group.length) return;
      var high = group[0].high;
      var low = group[0].low;
      for (var i = 1; i < group.length; i++) {
        if (group[i].high > high) high = group[i].high;
        if (group[i].low < low) low = group[i].low;
      }
      result.push({
        time: bucket,
        open: group[0].open,
        high: high,
        low: low,
        close: group[group.length - 1].close,
      });
    }
    for (var j = 0; j < candles.length; j++) {
      var c = candles[j];
      var bt = Math.floor(c.time / targetSec) * targetSec;
      if (bucket === null) bucket = bt;
      if (bt !== bucket) {
        flush();
        group = [c];
        bucket = bt;
      } else {
        group.push(c);
      }
    }
    flush();
    return result;
  }

  /** Nachkommastellen aus der Groessenordnung der Kurse ableiten (Krypto-Kleinpreise). */
  function priceFormatFor(candles) {
    var ref = candles.length ? candles[candles.length - 1].close : 1;
    var precision = ref >= 100 ? 2 : (ref >= 1 ? 4 : 6);
    return {
      type: 'price',
      precision: precision,
      minMove: Math.pow(10, -precision),
    };
  }

  /** Toolbar und Chart-Container in die Wurzel schreiben und die Elemente zurueckgeben. */
  function buildMarkup(root) {
    root.innerHTML =
      '<div class="chart-toolbar cp-toolbar mb-2">' +
      '  <div class="d-flex align-items-center gap-1 cc-tf-btns"></div>' +
      '  <div class="tf-separator"></div>' +
      '  <button type="button" class="tf-btn nav-btn cc-nav-start" title="Zum Anfang springen">&laquo;</button>' +
      '  <button type="button" class="tf-btn nav-btn cc-nav-end" title="Zum Ende springen">&raquo;</button>' +
      '  <button type="button" class="tf-btn nav-btn cc-fit" title="Alles anzeigen">Fit</button>' +
      '  <div class="tf-separator"></div>' +
      '  <button type="button" class="tf-btn cc-ruler" title="Preis-Differenz messen">Lineal</button>' +
      '  <button type="button" class="tf-btn cc-height" title="Charthöhe umschalten (400/560)">Höhe</button>' +
      '</div>' +
      '<div class="position-relative cc-container">' +
      '  <div class="cc-chart" style="width:100%; height:' + HEIGHT_NORMAL + 'px;"></div>' +
      '  <svg class="cc-ruler-overlay" style="position:absolute;inset:0;pointer-events:none;z-index:1000;display:none;"></svg>' +
      '  <div class="cc-ruler-label ruler-label"></div>' +
      '</div>';
    return {
      tfBtns: root.querySelector('.cc-tf-btns'),
      navStart: root.querySelector('.cc-nav-start'),
      navEnd: root.querySelector('.cc-nav-end'),
      fitBtn: root.querySelector('.cc-fit'),
      rulerBtn: root.querySelector('.cc-ruler'),
      heightBtn: root.querySelector('.cc-height'),
      container: root.querySelector('.cc-container'),
      chartEl: root.querySelector('.cc-chart'),
      rulerOverlay: root.querySelector('.cc-ruler-overlay'),
      rulerLabel: root.querySelector('.cc-ruler-label'),
    };
  }

  /**
   * Chart in die Wurzel haengen und die Candles des angegebenen Marktes laden.
   *
   * @param {HTMLElement} root Wurzel-Element (wird geleert und neu befuellt)
   * @param {Object} opts symbol, exchange, timeframe, start, end, storageKey
   * @returns {Promise<Object>} { chart, candleSeries } nach dem ersten Datenladen
   */
  function mount(root, opts) {
    var el = buildMarkup(root);
    var storagePrefix = 'candlechart.' + (opts.storageKey || 'default') + '.';

    var baseTf = opts.timeframe;
    var baseSec = TF_SEC[baseTf] || 0;
    var rawCandles = [];
    var visualTf = null;  // null = Basis-Zeitrahmen, kein Resampling
    var chart = null;
    var candleSeries = null;

    // --- Persistenz (Charthoehe und Anzeige-Zeitrahmen ueberleben den Reload) ---
    function storeGet(key) {
      try { return window.localStorage.getItem(storagePrefix + key); } catch (e) { return null; }
    }
    function storeSet(key, value) {
      try { window.localStorage.setItem(storagePrefix + key, value); } catch (e) { /* Storage gesperrt */ }
    }

    // --- Anzeige-Zeitrahmen ---
    function currentTargetSec() {
      return visualTf ? TF_SEC[visualTf] : baseSec;
    }

    function displayedCandles() {
      return visualTf ? resampleCandles(rawCandles, TF_SEC[visualTf]) : rawCandles;
    }

    /**
     * Startwert fuer den Anzeige-Zeitrahmen: gespeicherter Wert, sonst 1d (sofern die
     * Basis feiner ist). Ein gespeicherter Wert unterhalb der Basis waere nicht
     * darstellbar (die feineren Daten fehlen) und wird verworfen.
     */
    function initVisualTf() {
      var saved = storeGet('visualTf');
      if (saved === 'base') {
        visualTf = null;
        return;
      }
      if (saved && TF_SEC[saved] && TF_SEC[saved] > baseSec) {
        visualTf = saved;
        return;
      }
      visualTf = (baseSec && baseSec < TF_SEC['1d']) ? '1d' : null;
    }

    function renderTfButtons() {
      el.tfBtns.innerHTML = '';
      TF_LIST.filter(function (tf) { return TF_SEC[tf] >= baseSec; }).forEach(function (tf) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'tf-btn';
        b.textContent = tf;
        if ((!visualTf && tf === baseTf) || visualTf === tf) b.classList.add('active');
        b.addEventListener('click', function () {
          visualTf = (tf === baseTf) ? null : tf;
          storeSet('visualTf', visualTf || 'base');
          el.tfBtns.querySelectorAll('.tf-btn').forEach(function (x) { x.classList.remove('active'); });
          b.classList.add('active');
          applyVisualTf(false);
        });
        el.tfBtns.appendChild(b);
      });
    }

    /** Candles auf dem aktuellen Anzeige-Zeitrahmen neu setzen. */
    function applyVisualTf(preserveRange) {
      if (!candleSeries) return;
      var ts = chart.timeScale();
      var savedRange = preserveRange !== false ? ts.getVisibleLogicalRange() : null;
      candleSeries.setData(displayedCandles());
      ts.applyOptions({ timeVisible: currentTargetSec() < TF_SEC['1d'] });
      if (savedRange) ts.setVisibleLogicalRange(savedRange);
      else ts.fitContent();
      updateFitState();
    }

    // --- Fit ---
    /** Fit-Button leuchtet, solange der sichtbare Bereich die kompletten Daten abdeckt. */
    function updateFitState() {
      if (!chart || !candleSeries) return;
      var r = chart.timeScale().getVisibleLogicalRange();
      var n = (candleSeries.data() || []).length;
      if (!r || n === 0) {
        el.fitBtn.classList.remove('active');
        return;
      }
      el.fitBtn.classList.toggle('active', r.from <= 0.5 && r.to >= n - 1.5);
    }

    // --- Charthoehe ---
    function applyHeight(px) {
      el.chartEl.style.height = px + 'px';
      el.heightBtn.classList.toggle('active', px === HEIGHT_TALL);
    }

    // --- Lineal ---
    var rulerActive = false;
    var rulerStart = null;
    var rulerEnd = null;

    function clearRuler() {
      el.rulerOverlay.innerHTML = '';
      el.rulerOverlay.style.display = 'none';
      el.rulerLabel.style.display = 'none';
      rulerStart = null;
      rulerEnd = null;
    }

    function deactivateRuler() {
      rulerActive = false;
      el.rulerBtn.classList.remove('active');
      el.container.classList.remove('ruler-active');
    }

    /** Anzahl der Kerzen zwischen zwei Zeitpunkten im aktuellen Anzeige-Raster. */
    function barsBetween(t1, t2) {
      var data = candleSeries.data() || [];
      if (!data.length) return '-';
      var tMin = Math.min(t1, t2);
      var tMax = Math.max(t1, t2);
      var startIdx = -1;
      var endIdx = -1;
      for (var i = 0; i < data.length; i++) {
        if (startIdx === -1 && data[i].time >= tMin) startIdx = i;
        if (data[i].time >= tMax) { endIdx = i; break; }
      }
      return (startIdx !== -1 && endIdx !== -1) ? Math.abs(endIdx - startIdx) : '-';
    }

    function drawRulerLine() {
      if (!rulerStart || !rulerEnd || !candleSeries) return;
      var ts = chart.timeScale();
      var x1 = ts.timeToCoordinate(rulerStart.time);
      var y1 = candleSeries.priceToCoordinate(rulerStart.price);
      var x2 = ts.timeToCoordinate(rulerEnd.time);
      var y2 = candleSeries.priceToCoordinate(rulerEnd.price);
      if (x1 === null || y1 === null || x2 === null || y2 === null) {
        el.rulerOverlay.style.display = 'none';
        el.rulerLabel.style.display = 'none';
        return;
      }
      var w = el.container.clientWidth;
      var h = el.container.clientHeight;
      el.rulerOverlay.style.display = 'block';
      el.rulerOverlay.setAttribute('width', w);
      el.rulerOverlay.setAttribute('height', h);
      el.rulerOverlay.innerHTML =
        '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" stroke="#60a5fa" stroke-width="1.5" stroke-dasharray="6,3" />' +
        '<circle cx="' + x1 + '" cy="' + y1 + '" r="4" fill="#60a5fa" />' +
        '<circle cx="' + x2 + '" cy="' + y2 + '" r="4" fill="#60a5fa" />';

      var diff = rulerEnd.price - rulerStart.price;
      var pct = (diff / rulerStart.price) * 100;
      var isPos = diff >= 0;
      var sign = isPos ? '+' : '';
      el.rulerLabel.innerHTML =
        '<div class="ruler-percent ' + (isPos ? 'positive' : 'negative') + '">' + sign + pct.toFixed(2) + '%</div>' +
        '<div class="ruler-details">' + sign + diff.toFixed(rulerStart.price > 100 ? 2 : 6) +
        ' | ' + barsBetween(rulerStart.time, rulerEnd.time) + ' Kerzen</div>';

      var lx = (x1 + x2) / 2 + 10;
      var ly = (y1 + y2) / 2 - 20;
      if (lx > w - 150) lx = w - 150;
      if (lx < 10) lx = 10;
      if (ly < 10) ly = 10;
      if (ly > h - 50) ly = h - 50;
      el.rulerLabel.style.display = 'block';
      el.rulerLabel.style.left = lx + 'px';
      el.rulerLabel.style.top = ly + 'px';
    }

    function onChartClick(param) {
      if (!rulerActive || !param.point || !param.time) return;
      var price = candleSeries.coordinateToPrice(param.point.y);
      if (price === null || isNaN(price)) return;
      if (!rulerStart) {
        rulerStart = { time: param.time, price: price };
        el.rulerOverlay.style.display = 'block';
        el.rulerOverlay.setAttribute('width', el.container.clientWidth);
        el.rulerOverlay.setAttribute('height', el.container.clientHeight);
        el.rulerOverlay.innerHTML = '<circle cx="' + param.point.x + '" cy="' + param.point.y + '" r="4" fill="#60a5fa" />';
      } else if (!rulerEnd) {
        rulerEnd = { time: param.time, price: price };
        drawRulerLine();
        deactivateRuler();
      } else {
        clearRuler();
        rulerStart = { time: param.time, price: price };
      }
    }

    // --- Chart aufbauen ---
    function createChart() {
      chart = LightweightCharts.createChart(el.chartEl, {
        layout: { background: { color: 'transparent' }, textColor: getComputedStyle(document.body).color },
        grid: { vertLines: { color: 'rgba(128,128,128,0.12)' }, horzLines: { color: 'rgba(128,128,128,0.12)' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        timeScale: { timeVisible: true, secondsVisible: false },
        rightPriceScale: { borderColor: 'rgba(128,128,128,0.3)' },
        autoSize: true,
      });
      candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: '#2fb344', downColor: '#d63939', borderVisible: false,
        wickUpColor: '#2fb344', wickDownColor: '#d63939',
      });
      chart.subscribeClick(onChartClick);
      chart.timeScale().subscribeVisibleLogicalRangeChange(function () {
        updateFitState();
        if (rulerStart && rulerEnd) drawRulerLine();
      });
    }

    // --- Bedienelemente verdrahten ---
    el.fitBtn.addEventListener('click', function () {
      this.blur();
      chart.timeScale().fitContent();
      updateFitState();
    });

    el.navStart.addEventListener('click', function () {
      this.blur();
      var ts = chart.timeScale();
      var r = ts.getVisibleLogicalRange();
      var visible = r ? Math.round(r.to - r.from) : 100;
      ts.setVisibleLogicalRange({ from: -2, to: visible });
    });

    el.navEnd.addEventListener('click', function () {
      this.blur();
      chart.timeScale().scrollToRealTime();
    });

    el.heightBtn.addEventListener('click', function () {
      this.blur();
      var next = el.chartEl.offsetHeight > (HEIGHT_NORMAL + HEIGHT_TALL) / 2 ? HEIGHT_NORMAL : HEIGHT_TALL;
      applyHeight(next);
      storeSet('height', String(next));
    });

    el.rulerBtn.addEventListener('click', function () {
      this.blur();
      rulerActive = !rulerActive;
      el.rulerBtn.classList.toggle('active', rulerActive);
      el.container.classList.toggle('ruler-active', rulerActive);
      clearRuler();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && (rulerActive || rulerStart)) {
        deactivateRuler();
        clearRuler();
      }
    });

    window.addEventListener('resize', function () {
      if (rulerStart && rulerEnd) drawRulerLine();
    });

    // --- Initialisierung: Layout wiederherstellen, Candles laden ---
    applyHeight(parseInt(storeGet('height'), 10) === HEIGHT_TALL ? HEIGHT_TALL : HEIGHT_NORMAL);
    initVisualTf();
    renderTfButtons();
    createChart();

    var params = new URLSearchParams({
      symbol: opts.symbol,
      exchange: opts.exchange,
      timeframe: opts.timeframe,
    });
    if (opts.start) params.set('start', opts.start);
    if (opts.end) params.set('end', opts.end);

    return fetch('/api/chart-playground/ohlcv?' + params.toString())
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (payload) {
        rawCandles = (payload.data && payload.data.candles) || [];
        candleSeries.applyOptions({ priceFormat: priceFormatFor(rawCandles) });
        applyVisualTf(false);
        return { chart: chart, candleSeries: candleSeries };
      });
  }

  window.CandleChart = { mount: mount, resampleCandles: resampleCandles };
})(window, document);
