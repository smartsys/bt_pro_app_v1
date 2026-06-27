/**
 * result/overlay.js
 *
 * Gemeinsame Chart-Renderer für Equity-Sub-Chart und Trade-Marker.
 * Wird sowohl von result_chart.html als auch vom Chart-Playground eingebunden.
 *
 * Öffentliche API:
 *   ResultOverlay.renderEquityCurve(resultId, chart, candleSeries, opts)
 *   ResultOverlay.renderTradeMarkers(resultId, chart, candleSeries, opts)
 *   ResultOverlay.removeTradeMarkers(candleSeries, markerRef)
 *
 * renderEquityCurve opts:
 *   equityData    — optional vorgeladene Equity-Daten [{time, value}]
 *   onSeries      — Callback(equitySeries) nach Anlegen der Series
 *   minTime       — optionaler Mindest-Timestamp für Filter
 *
 * renderTradeMarkers opts:
 *   tradesData    — optional vorgeladene Trade-Daten (Array)
 *   containerEl   — HTMLElement des Charts für Tooltip-Positionierung
 *   tooltipEl     — HTMLElement für Order-Tooltip
 *   isDark        — boolean, Dark-Mode-Flag
 *   onPrimitive   — Callback(orderPrimitive) nach Anlegen
 */
(function(global) {
  'use strict';

  // -----------------------------------------------------------------------
  // OrderPrimitive (Trade-Marker) — identisch mit result_chart.html
  // -----------------------------------------------------------------------

  function OrderPrimitive(trades, chart, candleSeries, isDark) {
    this._trades = trades || [];
    this._chart = chart;
    this._candleSeries = candleSeries;
    this._isDark = !!isDark;
    this._hitAreas = [];
  }
  OrderPrimitive.prototype.paneViews = function() {
    return [new OrderPaneView(this._trades, this)];
  };
  OrderPrimitive.prototype.setHitAreas = function(areas) { this._hitAreas = areas; };
  OrderPrimitive.prototype.getHitAreas = function() { return this._hitAreas; };

  function OrderPaneView(trades, primitive) {
    this._trades = trades;
    this._primitive = primitive;
  }
  OrderPaneView.prototype.renderer = function() {
    return new OrderRenderer(this._trades, this._primitive);
  };

  function OrderRenderer(trades, primitive) {
    this._trades = trades;
    this._primitive = primitive;
  }
  OrderRenderer.prototype.draw = function(target) {
    var trades = this._trades;
    var primitive = this._primitive;
    var chart = primitive._chart;
    var series = primitive._candleSeries;
    var isDark = primitive._isDark;

    target.useBitmapCoordinateSpace(function(scope) {
      if (!scope.horizontalPixelRatio || !scope.verticalPixelRatio) return;
      var ctx = scope.context;
      var pr = scope.horizontalPixelRatio;
      var vr = scope.verticalPixelRatio;
      var ts = chart.timeScale();
      var visibleRange = ts.getVisibleRange();
      var hitAreas = [];

      trades.forEach(function(t, tIdx) {
        if (visibleRange && (t.entry_time > visibleRange.to || t.exit_time < visibleRange.from)) return;
        var startX = ts.timeToCoordinate(t.entry_time);
        var endX = ts.timeToCoordinate(t.exit_time);
        if (startX === null || endX === null) return;
        var entryY = series.priceToCoordinate(t.entry_price);
        var exitY = series.priceToCoordinate(t.exit_price);
        if (entryY === null || exitY === null) return;

        var isProfit = t.pnl && t.pnl >= 0;
        var borderColor = isProfit ? '#2fb344' : '#d63939';
        var x = Math.round(Math.max(0, startX) * pr);
        var entryYB = Math.round(entryY * vr);
        var exitYB = Math.round(exitY * vr);
        var width = Math.round((Math.min(scope.bitmapSize.width / pr, endX) - Math.max(0, startX)) * pr);
        if (width <= 2) return;

        // TP/SL
        var tpYB = null, slYB = null;
        if (t.tp_price) { var tpY = series.priceToCoordinate(t.tp_price); if (tpY !== null) tpYB = Math.round(tpY * vr); }
        if (t.sl_price) { var slY = series.priceToCoordinate(t.sl_price); if (slY !== null) slYB = Math.round(slY * vr); }

        ctx.save();

        // Hintergrund
        var topY = Math.min(entryYB, exitYB);
        var bgH = Math.abs(exitYB - entryYB);
        if (bgH < 4) bgH = 4;
        ctx.fillStyle = isProfit ? 'rgba(47,179,68,0.12)' : 'rgba(214,57,57,0.12)';
        ctx.fillRect(x, topY, width, bgH);

        // Gestrichelte Linien
        ctx.globalAlpha = 0.8;
        ctx.lineWidth = 1.5 * pr;
        ctx.setLineDash([6 * pr, 4 * pr]);

        ctx.strokeStyle = isDark ? '#e5e7eb' : '#000000';
        ctx.beginPath(); ctx.moveTo(x, entryYB); ctx.lineTo(x + width, entryYB); ctx.stroke();

        if (tpYB !== null) {
          ctx.strokeStyle = '#2fb344';
          ctx.beginPath(); ctx.moveTo(x, tpYB); ctx.lineTo(x + width, tpYB); ctx.stroke();
        }
        if (slYB !== null) {
          ctx.strokeStyle = '#d63939';
          ctx.beginPath(); ctx.moveTo(x, slYB); ctx.lineTo(x + width, slYB); ctx.stroke();
        }

        ctx.setLineDash([]);
        ctx.globalAlpha = 1.0;

        // Entry-Marker
        var mr = 5 * pr;
        ctx.beginPath(); ctx.arc(x, entryYB, mr, 0, 2 * Math.PI);
        ctx.fillStyle = isDark ? '#e5e7eb' : '#000000'; ctx.fill();
        ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.5 * pr; ctx.stroke();
        ctx.beginPath(); ctx.arc(x, entryYB, 2 * pr, 0, 2 * Math.PI);
        ctx.fillStyle = '#ffffff'; ctx.fill();

        // Exit-Marker
        ctx.beginPath(); ctx.arc(x + width, exitYB, mr, 0, 2 * Math.PI);
        ctx.fillStyle = borderColor; ctx.fill();
        ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.5 * pr; ctx.stroke();

        ctx.restore();

        // P&L-Text
        if (t.return_pct !== null && t.return_pct !== undefined) {
          var pnlText = (t.return_pct >= 0 ? '+' : '') + t.return_pct.toFixed(2) + '%';
          ctx.font = 'bold ' + (11 * pr) + 'px Arial';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'middle';
          var textX = x + width + 6 * pr;
          var textW = ctx.measureText(pnlText).width;
          var textH = 14 * vr;
          ctx.fillStyle = isProfit ? 'rgba(47,179,68,0.9)' : 'rgba(214,57,57,0.9)';
          var pillX = textX - 3 * pr, pillY = exitYB - textH / 2;
          var pillW = textW + 6 * pr, pillR = 3 * pr;
          ctx.beginPath();
          ctx.moveTo(pillX + pillR, pillY); ctx.lineTo(pillX + pillW - pillR, pillY);
          ctx.quadraticCurveTo(pillX + pillW, pillY, pillX + pillW, pillY + pillR);
          ctx.lineTo(pillX + pillW, pillY + textH - pillR);
          ctx.quadraticCurveTo(pillX + pillW, pillY + textH, pillX + pillW - pillR, pillY + textH);
          ctx.lineTo(pillX + pillR, pillY + textH);
          ctx.quadraticCurveTo(pillX, pillY + textH, pillX, pillY + textH - pillR);
          ctx.lineTo(pillX, pillY + pillR);
          ctx.quadraticCurveTo(pillX, pillY, pillX + pillR, pillY);
          ctx.fill();
          ctx.fillStyle = '#ffffff';
          ctx.fillText(pnlText, textX, exitYB);
        }

        // Hitboxen
        var hitRadius = 12;
        hitAreas.push({ cx: startX, cy: entryY, radius: hitRadius, type: 'Entry', tradeIdx: tIdx, trade: t });
        hitAreas.push({ cx: endX, cy: exitY, radius: hitRadius, type: 'Exit', tradeIdx: tIdx, trade: t });
      });

      if (primitive) primitive.setHitAreas(hitAreas);
    });
  };

  // -----------------------------------------------------------------------
  // Tooltip-Hilfsfunktionen
  // -----------------------------------------------------------------------

  function buildTooltipHtml(hit) {
    var t = hit.trade;
    var isEntry = hit.type === 'Entry';
    var time = isEntry ? t.entry_time : t.exit_time;
    var price = isEntry ? t.entry_price : t.exit_price;
    var orderId = isEntry ? t.entry_order_id : t.exit_order_id;
    var side = isEntry ? 'Buy' : 'Sell';
    var tradeId = t.trade_id !== undefined ? t.trade_id : t.trade_idx;
    var prec = price > 100 ? 2 : (price > 1 ? 4 : 8);
    var date = new Date(time * 1000);
    var dateStr = date.toLocaleDateString('de-DE') + ' ' + date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    var priceStr = price.toLocaleString('de-DE', { minimumFractionDigits: prec, maximumFractionDigits: prec });

    // Dauer clientseitig berechnen (exit_time - entry_time)
    var durationStr = '';
    if (t.entry_time && t.exit_time) {
      var durSec = t.exit_time - t.entry_time;
      var durH = Math.floor(durSec / 3600);
      var durD = Math.floor(durH / 24);
      if (durD > 0) durationStr = durD + 'd ' + (durH % 24) + 'h';
      else if (durH > 0) durationStr = durH + 'h';
      else durationStr = Math.round(durSec / 60) + 'min';
    }

    var html = '<b>' + side + ' #' + tradeId + '</b> | ' + (t.direction || 'long') + '<br>';
    html += '<span style="color:#888">Seite: ' + (t.direction || 'long') + '</span><br>';
    html += 'Preis: ' + priceStr + '<br>';
    if (durationStr) html += 'Dauer: ' + durationStr + '<br>';
    html += 'Zeit: ' + dateStr;
    if (!isEntry && t.entry_price && t.exit_price) {
      html += '<br>Entry: ' + t.entry_price.toLocaleString('de-DE', { minimumFractionDigits: prec, maximumFractionDigits: prec });
      html += ' / Exit: ' + t.exit_price.toLocaleString('de-DE', { minimumFractionDigits: prec, maximumFractionDigits: prec });
    }
    if (!isEntry && t.return_pct !== null && t.return_pct !== undefined) {
      var plStr = (t.return_pct >= 0 ? '+' : '') + t.return_pct.toFixed(2) + '%';
      var plColor = t.return_pct >= 0 ? '#a6e3a1' : '#f38ba8';
      html += '<br>P&amp;L: <span style="color:' + plColor + '">' + plStr + '</span>';
    }
    if (!isEntry && t.exit_stop_type && t.exit_stop_type !== 'None') {
      html += ' | Exit: ' + t.exit_stop_type;
    }
    return html;
  }

  function findHitArea(mouseX, mouseY, orderPrimitive) {
    if (!orderPrimitive) return null;
    var hitAreas = orderPrimitive.getHitAreas();
    if (!hitAreas || hitAreas.length === 0) return null;
    for (var i = 0; i < hitAreas.length; i++) {
      var a = hitAreas[i];
      var dx = mouseX - a.cx, dy = mouseY - a.cy;
      if (dx * dx + dy * dy <= a.radius * a.radius) return a;
    }
    return null;
  }

  // -----------------------------------------------------------------------
  // renderEquityCurve
  // -----------------------------------------------------------------------

  /**
   * Lädt Equity-Daten und fügt eine Equity-Line-Series zum Chart hinzu.
   * Gibt ein Promise<equitySeries> zurück.
   *
   * @param {number} resultId
   * @param {Object} chart   — LightweightCharts-Instanz
   * @param {Object} opts
   */
  function renderEquityCurve(resultId, chart, opts) {
    opts = opts || {};

    function doRender(equityData) {
      if (!equityData || equityData.length === 0) return null;
      var minTime = opts.minTime || 0;
      var filtered = equityData.filter(function(e) { return e.value != null && e.time >= minTime; });
      if (filtered.length === 0) return null;

      var equitySeries = chart.addSeries(LightweightCharts.LineSeries, {
        color: '#3b82f6', lineWidth: 2, priceScaleId: 'equity',
        title: 'Equity', lastValueVisible: true, priceLineVisible: false,
      });
      chart.priceScale('equity').applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 } });
      equitySeries.setData(filtered);

      if (opts.onSeries) opts.onSeries(equitySeries);
      return equitySeries;
    }

    if (opts.equityData) {
      return Promise.resolve(doRender(opts.equityData));
    }

    return fetch('/api/backtest/results/' + resultId + '/chart-data')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        return doRender(data.equity || []);
      });
  }

  // -----------------------------------------------------------------------
  // renderTradeMarkers
  // -----------------------------------------------------------------------

  /**
   * Lädt Trade-Daten und hängt einen OrderPrimitive an die candleSeries.
   * Gibt ein Promise<orderPrimitive> zurück.
   *
   * @param {number} resultId
   * @param {Object} chart
   * @param {Object} candleSeries
   * @param {Object} opts
   */
  function renderTradeMarkers(resultId, chart, candleSeries, opts) {
    opts = opts || {};
    var isDark = !!opts.isDark;
    var containerEl = opts.containerEl || null;
    var tooltipEl = opts.tooltipEl || null;

    function doRender(trades) {
      if (!trades || trades.length === 0) return null;
      var primitive = new OrderPrimitive(trades, chart, candleSeries, isDark);
      candleSeries.attachPrimitive(primitive);
      // Redraw erzwingen
      candleSeries.detachPrimitive(primitive);
      candleSeries.attachPrimitive(primitive);

      // Tooltip-Events nur einmal registrieren (per containerEl)
      if (containerEl && tooltipEl && !containerEl._resultOverlayTooltipBound) {
        containerEl._resultOverlayTooltipBound = true;
        var pinnedPrimitive = null;
        var tooltipPinned = false;

        containerEl.addEventListener('mousemove', function(e) {
          if (tooltipPinned || !containerEl._currentPrimitive) return;
          var rect = containerEl.getBoundingClientRect();
          var mx = e.clientX - rect.left, my = e.clientY - rect.top;
          var hit = findHitArea(mx, my, containerEl._currentPrimitive);
          if (hit) {
            tooltipEl.innerHTML = buildTooltipHtml(hit);
            tooltipEl.style.display = 'block';
            tooltipEl.style.borderColor = '#585b70';
            tooltipEl.style.left = '0'; tooltipEl.style.top = '0';
            var ttW = tooltipEl.offsetWidth, ttH = tooltipEl.offsetHeight;
            var ttX = mx - ttW / 2, ttY = hit.cy - ttH - 15;
            if (ttX < 5) ttX = 5;
            if (ttX + ttW > rect.width - 5) ttX = rect.width - ttW - 5;
            if (ttY < 5) ttY = hit.cy + 15;
            tooltipEl.style.left = ttX + 'px'; tooltipEl.style.top = ttY + 'px';
            containerEl.style.cursor = 'pointer';
          } else {
            tooltipEl.style.display = 'none';
            containerEl.style.cursor = 'default';
          }
        });
        containerEl.addEventListener('click', function(e) {
          if (!containerEl._currentPrimitive) return;
          var rect = containerEl.getBoundingClientRect();
          var mx = e.clientX - rect.left, my = e.clientY - rect.top;
          var hit = findHitArea(mx, my, containerEl._currentPrimitive);
          if (tooltipPinned) {
            tooltipPinned = false; tooltipEl.style.display = 'none'; containerEl.style.cursor = 'default';
          } else if (hit) {
            tooltipPinned = true;
            tooltipEl.innerHTML = buildTooltipHtml(hit);
            tooltipEl.style.display = 'block';
            tooltipEl.style.borderColor = '#3b82f6';
            navigator.clipboard && navigator.clipboard.writeText(tooltipEl.textContent).catch(function() {});
          }
        });
        containerEl.addEventListener('mouseleave', function() {
          if (!tooltipPinned) tooltipEl.style.display = 'none';
        });
        document.addEventListener('keydown', function(e) {
          if (e.key === 'Escape') { tooltipPinned = false; tooltipEl.style.display = 'none'; }
        });
      }

      // Primitive für Tooltip-Handler referenzieren
      if (containerEl) containerEl._currentPrimitive = primitive;

      if (opts.onPrimitive) opts.onPrimitive(primitive);
      return primitive;
    }

    if (opts.tradesData) {
      return Promise.resolve(doRender(opts.tradesData));
    }

    return fetch('/api/backtest/results/' + resultId + '/trades')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        return doRender(data.trades || []);
      });
  }

  /**
   * Entfernt einen bestehenden OrderPrimitive sicher vom candleSeries.
   * @param {Object} candleSeries
   * @param {Object|null} primitive
   */
  function removeTradeMarkers(candleSeries, primitive) {
    if (!primitive || !candleSeries) return;
    try { candleSeries.detachPrimitive(primitive); } catch (e) {}
  }

  // -----------------------------------------------------------------------
  // attachEquityTooltip
  // -----------------------------------------------------------------------

  /**
   * Hängt einen Klick-Handler an den Chart-Container, der bei Klick nahe der
   * Equity-Linie ein Label mit dem aktuellen Equity-Wert anzeigt.
   *
   * @param {Object} chart        — LightweightCharts-Instanz
   * @param {HTMLElement} containerEl — Chart-Container (für Klick + Breite)
   * @param {HTMLElement} tooltipEl   — absolut positioniertes Tooltip-Element
   * @param {Function} getEquitySeries — liefert die aktuelle Equity-Series (oder null)
   */
  function attachEquityTooltip(chart, containerEl, tooltipEl, getEquitySeries) {
    if (!chart || !containerEl || !tooltipEl) return;
    var lastCrosshairParam = null;
    chart.subscribeCrosshairMove(function(param) { lastCrosshairParam = param; });
    containerEl.addEventListener("click", function() {
      var equitySeries = getEquitySeries ? getEquitySeries() : null;
      if (!equitySeries || !lastCrosshairParam || !lastCrosshairParam.time || !lastCrosshairParam.point) {
        tooltipEl.style.display = 'none';
        return;
      }
      var eqData = lastCrosshairParam.seriesData.get(equitySeries);
      if (!eqData || eqData.value === undefined) {
        tooltipEl.style.display = 'none';
        return;
      }
      // Nur anzeigen wenn Klick nahe an der Equity-Linie (max 10px Abstand)
      var eqY;
      try { eqY = equitySeries.priceToCoordinate(eqData.value); } catch (e) { eqY = null; }
      if (eqY === null || Math.abs(lastCrosshairParam.point.y - eqY) > 10) {
        tooltipEl.style.display = 'none';
        return;
      }
      tooltipEl.textContent = 'Equity: ' + eqData.value.toFixed(2);
      tooltipEl.style.display = 'block';
      var x = lastCrosshairParam.point.x + 12;
      var y = lastCrosshairParam.point.y - 24;
      if (x + tooltipEl.offsetWidth > containerEl.clientWidth) x = lastCrosshairParam.point.x - tooltipEl.offsetWidth - 12;
      if (y < 0) y = lastCrosshairParam.point.y + 12;
      tooltipEl.style.left = x + 'px';
      tooltipEl.style.top = y + 'px';
    });
  }

  // -----------------------------------------------------------------------
  // Exports
  // -----------------------------------------------------------------------
  global.ResultOverlay = {
    renderEquityCurve: renderEquityCurve,
    attachEquityTooltip: attachEquityTooltip,
    renderTradeMarkers: renderTradeMarkers,
    removeTradeMarkers: removeTradeMarkers,
    // OrderPrimitive öffentlich machen für TF-Resampling im Playground
    OrderPrimitive: OrderPrimitive,
    buildTooltipHtml: buildTooltipHtml,
  };

})(window);
