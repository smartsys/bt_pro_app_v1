/**
 * result/tabs.js
 *
 * Gemeinsame Tab-Loader für Stats und Trades/Orders/Positions.
 * Wird sowohl von result_chart.html als auch vom Chart-Playground eingebunden.
 *
 * Öffentliche API:
 *   ResultTabs.loadStatsTab(resultId, opts)
 *   ResultTabs.loadTradesTab(resultId, opts)
 *
 * opts für loadStatsTab:
 *   contentEl      — HTMLElement für den Stats-Inhalt (Pflicht)
 *   fullMetricsBarEl — HTMLElement für die Vollanalyse-Bar (optional)
 *   extendedMetricsEl — HTMLElement für Erweiterte Metriken (optional)
 *   extendedMetricsContentEl — HTMLElement für Inhalt der erweiterten Metriken (optional)
 *   benchmarkValueEl — HTMLElement für Benchmark-Wert in der Metrik-Leiste (optional)
 *   onStatsLoaded  — Callback(statsData) nach erfolgreichem Laden (optional)
 *
 * opts für loadTradesTab:
 *   contentEl      — HTMLElement (Pflicht)
 */
(function(global) {
  'use strict';

  // -----------------------------------------------------------------------
  // Hilfsfunktionen (lokal, nicht öffentlich)
  // -----------------------------------------------------------------------

  /** Formatiert einen ISO-8601-Duration-String in lesbare Form. */
  function fmtDuration(v) {
    if (!v || typeof v !== 'string' || v.indexOf('P') !== 0) return fmtVal(v);
    var m = v.match(/P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
    if (!m) return v;
    var parts = [];
    if (m[1] && m[1] !== '0') parts.push(m[1] + 'd');
    if (m[2] && m[2] !== '0') parts.push(m[2] + 'h');
    if (m[3] && m[3] !== '0') parts.push(m[3] + 'm');
    if (m[4] && m[4] !== '0') parts.push(m[4] + 's');
    return parts.length ? parts.join(' ') : '0';
  }

  /** Formatiert einen Zahlenwert oder gibt '—' zurück. */
  function fmtVal(v) {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'number') return parseFloat(v.toPrecision(6)).toString();
    return String(v);
  }

  /** Formatiert einen ISO-Datum-String in dd.mm.yyyy HH:MM. */
  function fmtDate(v) {
    if (!v || typeof v !== 'string') return fmtVal(v);
    try {
      var d = new Date(v);
      if (isNaN(d.getTime())) return v;
      return d.getDate().toString().padStart(2, '0') + '.' +
        (d.getMonth() + 1).toString().padStart(2, '0') + '.' +
        d.getFullYear() + ' ' +
        d.getHours().toString().padStart(2, '0') + ':' +
        d.getMinutes().toString().padStart(2, '0');
    } catch (e) { return v; }
  }

  /** Formatiert einen Unix-Timestamp in de-DE-Locale. */
  function fmtTs(ts) {
    return ts ? new Date(ts * 1000).toLocaleString('de-DE') : '—';
  }

  /** Formatiert eine Zahl mit d Nachkommastellen. */
  function fmtNum(v, d) {
    return v != null ? v.toFixed(d) : '—';
  }

  // -----------------------------------------------------------------------
  // Stats-Tab
  // -----------------------------------------------------------------------

  /**
   * Baut die Tooltip-Initialisierung für dynamisch eingefügte Elemente.
   * @param {HTMLElement} container
   */
  function initTooltips(container) {
    container.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function(el) {
      var tipText = el.getAttribute('title') || '';
      el.removeAttribute('title');
      el.setAttribute('data-tip', tipText);
      el.addEventListener('mouseenter', function() {
        var text = el.getAttribute('data-tip');
        if (!text) return;
        var rect = el.getBoundingClientRect();
        var tip = document.createElement('div');
        tip.className = 'tooltip bs-tooltip-top show';
        tip.setAttribute('role', 'tooltip');
        tip.innerHTML = '<div class="tooltip-arrow"></div><div class="tooltip-inner" style="font-size:0.85rem">' + text + '</div>';
        document.body.appendChild(tip);
        tip.style.position = 'fixed';
        tip.style.left = (rect.left + rect.width / 2 - tip.offsetWidth / 2) + 'px';
        tip.style.top = (rect.top - tip.offsetHeight - 4) + 'px';
        el._tip = tip;
      });
      el.addEventListener('mouseleave', function() {
        if (el._tip) { el._tip.remove(); el._tip = null; }
      });
    });
  }

  /**
   * Rendert die erweiterten Metriken in einen Container.
   * @param {Object} s  — Stats-Objekt
   * @param {string} level  — 'basic' | 'full'
   * @param {HTMLElement} card  — .extended-metrics-Wrapper
   * @param {HTMLElement} container  — .extended-metrics-content
   */
  function buildExtendedMetrics(s, level, card, container) {
    if (!card || !container) return;

    var tipIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-muted" style="vertical-align:-0.1em;"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0"/><path d="M12 9h.01"/><path d="M11 12h1v4h1"/></svg>';
    function tip(text) {
      return ' <span class="ms-1" style="vertical-align:baseline;" data-bs-toggle="tooltip" data-bs-placement="top" title="' + text + '">' + tipIcon + '</span>';
    }

    var fmtExt = function(v) {
      if (v === null || v === undefined) return '<span class="text-muted">—</span>';
      var num = parseFloat(v);
      if (isNaN(num)) return '<span class="text-muted">—</span>';
      return parseFloat(num.toPrecision(6)).toString();
    };

    var col1 = [
      ['Annualisierte Rendite [%]', 'Annualized Return [%]', 'Jahresrendite — macht verschiedene Backtestzeiträume vergleichbar'],
      ['Annualisierte Volatilität [%]', 'Annualized Volatility [%]', 'Jährliche Schwankungsbreite — hohe Volatilität = hohes Risiko'],
      ['Downside Risk [%]', 'Downside Risk [%]', 'Nur negative Volatilität — bestraft nur Verluste, nicht Gewinne'],
      ['Deflated Sharpe Ratio', 'Deflated Sharpe Ratio', 'Korrigierter Sharpe für Multiple-Testing — berücksichtigt Overfitting bei vielen Kombinationen'],
    ];
    var col2 = [
      ['SQN (System Quality)', 'SQN', 'Van Tharp System Quality Number — <1.7 schlecht, 1.7-2.5 durchschnittlich, 2.5-4 gut, >4 exzellent'],
      ['Edge Ratio', 'Edge Ratio', 'MFE/MAE Verhältnis — wie gut Gewinne mitgenommen vs. Verluste begrenzt werden'],
    ];
    var col3 = [
      ['Alpha', 'Alpha', 'Überrendite gegenüber Benchmark — positiv = Strategie schlägt den Markt'],
      ['Beta', 'Beta', 'Markt-Sensitivität — 1 = wie Markt, <1 defensiver, >1 aggressiver'],
      ['Information Ratio', 'Information Ratio', 'Überrendite pro Tracking-Error — wie konsistent die Benchmark geschlagen wird'],
      ['Tail Ratio', 'Tail Ratio', 'Gewinn- vs. Verlust-Extremwerte — >1 = Gewinne sind extremer als Verluste'],
      ['Value at Risk', 'Value at Risk', 'Maximaler erwarteter Tagesverlust (95%) unter normalen Bedingungen'],
      ['Conditional VaR', 'Conditional VaR', 'Erwarteter Verlust im Worst Case — wenn VaR überschritten wird'],
    ];

    function buildTbl(items) {
      var h = '<table class="table table-sm table-striped mb-0"><tbody>';
      items.forEach(function(item) {
        h += '<tr><td>' + item[0] + tip(item[2]) + '</td><td>' + fmtExt(s[item[1]]) + '</td></tr>';
      });
      return h + '</tbody></table>';
    }

    var html = '<div class="col-md-4"><h6 class="mb-2">Rendite &amp; Risiko</h6>' + buildTbl(col1) + '</div>' +
      '<div class="col-md-4"><h6 class="mb-2">Trade-Qualität</h6>' + buildTbl(col2) + '</div>' +
      '<div class="col-md-4"><h6 class="mb-2">Benchmark &amp; Extremrisiko</h6>' + buildTbl(col3) + '</div>';

    if (level !== 'full') {
      html += '<div class="col-12 mt-2"><div class="text-muted small">Trade-Qualität, Benchmark- und Extremrisiko-Metriken werden erst nach der Vollanalyse befüllt.</div></div>';
    }

    container.innerHTML = html;
    card.style.display = '';
    initTooltips(container);
  }

  /**
   * Aktualisiert den Vollanalyse-Button-Zustand.
   * @param {string} level
   * @param {HTMLElement} bar
   * @param {HTMLElement} btn
   */
  function updateMetricsLevelUI(level, bar, btn) {
    if (!bar || !btn) return;
    bar.style.cssText = '';
    if (level === 'full') {
      btn.className = 'btn btn-success';
      btn.innerHTML = 'Vollanalyse abgeschlossen';
      btn.disabled = true;
    } else {
      btn.className = 'btn btn-primary';
      btn.innerHTML = 'Vollanalyse starten';
      btn.disabled = false;
    }
  }

  /**
   * Lädt Stats-Tab-Inhalte via AJAX.
   *
   * @param {number} resultId
   * @param {Object} opts
   */
  function loadStatsTab(resultId, opts) {
    opts = opts || {};
    var contentEl = opts.contentEl;
    var fullMetricsBarEl = opts.fullMetricsBarEl || null;
    var extendedMetricsEl = opts.extendedMetricsEl || null;
    var extendedMetricsContentEl = opts.extendedMetricsContentEl || null;
    var benchmarkValueEl = opts.benchmarkValueEl || null;
    var onStatsLoaded = opts.onStatsLoaded || null;

    if (!contentEl) return;
    contentEl.innerHTML = '<div class="text-muted">Stats werden geladen...</div>';

    fetch('/api/backtest/results/' + resultId + '/stats')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data.stats) {
          contentEl.innerHTML = '<div class="text-muted">Stats noch nicht berechnet.</div>';
          return;
        }

        // Metrics-Level UI aktualisieren
        if (data.metrics_level && fullMetricsBarEl) {
          var btn = fullMetricsBarEl.querySelector('[data-full-metrics-btn]');
          updateMetricsLevelUI(data.metrics_level, fullMetricsBarEl, btn);
        }

        var s = data.stats;

        // Linke und rechte Spalte der Stats-Tabelle
        var leftCol = [
          ['Start Value', 'Start Value', fmtVal],
          ['End Value', 'End Value', fmtVal],
          ['Total Return [%]', 'Total Return [%]', fmtVal],
          ['Benchmark Return [%]', 'Benchmark Return [%]', fmtVal],
          ['Total Orders', 'Total Orders', fmtVal],
          ['Total Trades', 'Total Trades', fmtVal],
          ['Win Rate [%]', 'Win Rate [%]', fmtVal],
          ['Best Trade [%]', 'Best Trade [%]', fmtVal],
          ['Profit Factor', 'Profit Factor', fmtVal],
          ['Worst Trade [%]', 'Worst Trade [%]', fmtVal],
          ['Max Drawdown [%]', 'Max Drawdown [%]', fmtVal],
          ['Avg Losing Trade [%]', 'Avg Losing Trade [%]', fmtVal],
          ['Avg Winning Trade [%]', 'Avg Winning Trade [%]', fmtVal],
          ['Max Drawdown Duration', 'Max Drawdown Duration', fmtDuration],
        ];
        var rightCol = [
          ['Max Value', 'Max Value', fmtVal],
          ['Min Value', 'Min Value', fmtVal],
          ['Expectancy', 'Expectancy', fmtVal],
          ['Omega Ratio', 'Omega Ratio', fmtVal],
          ['Calmar Ratio', 'Calmar Ratio', fmtVal],
          ['Sharpe Ratio', 'Sharpe Ratio', fmtVal],
          ['Sortino Ratio', 'Sortino Ratio', fmtVal],
          ['Total Duration', 'Total Duration', fmtDuration],
          ['Total Fees Paid', 'Total Fees Paid', fmtVal],
          ['Position Coverage [%]', 'Position Coverage [%]', fmtVal],
          ['Max Gross Exposure [%]', 'Max Gross Exposure [%]', fmtVal],
          ['Avg Losing Trade Duration', 'Avg Losing Trade Duration', fmtDuration],
          ['Avg Winning Trade Duration', 'Avg Winning Trade Duration', fmtDuration],
          ['Start Index', 'Start Index', fmtDate],
          ['End Index', 'End Index', fmtDate],
        ];

        function buildTable(cols) {
          var h = '<table class="table table-sm table-striped mb-0"><thead><tr><th>Metrik</th><th>Wert</th></tr></thead><tbody>';
          cols.forEach(function(c) {
            h += '<tr><td>' + c[0] + '</td><td>' + c[2](s[c[1]]) + '</td></tr>';
          });
          return h + '</tbody></table>';
        }

        contentEl.innerHTML = '<div class="row"><div class="col-md-6">' +
          buildTable(leftCol) + '</div><div class="col-md-6">' +
          buildTable(rightCol) + '</div></div>';

        // Erweiterte Metriken befüllen
        buildExtendedMetrics(s, data.metrics_level, extendedMetricsEl, extendedMetricsContentEl);

        // Benchmark-Wert aktualisieren
        if (benchmarkValueEl) {
          var bm = s['Benchmark Return [%]'];
          if (bm != null) {
            benchmarkValueEl.textContent = parseFloat(bm).toFixed(2) + '%';
            benchmarkValueEl.className = 'metric-value ' + (bm >= 0 ? 'val-pos' : 'val-neg');
          }
        }

        // Callback mit kompletten Daten (für Playground: Win-Rate, PF, AvgDuration)
        if (onStatsLoaded) onStatsLoaded(data);
      })
      .catch(function(err) {
        contentEl.innerHTML = '<div class="text-danger">Fehler beim Laden: ' + err.message + '</div>';
      });
  }

  // -----------------------------------------------------------------------
  // Trades-Tab
  // -----------------------------------------------------------------------

  /**
   * Lädt Trades/Orders/Positions-Tab via AJAX.
   *
   * @param {number} resultId
   * @param {Object} opts
   *   contentEl — HTMLElement
   *   tradesData — optional vorgeladene Trade-Daten (vermeidet zweiten Fetch)
   */
  function loadTradesTab(resultId, opts) {
    opts = opts || {};
    var contentEl = opts.contentEl;
    if (!contentEl) return;

    contentEl.innerHTML = '<div class="text-muted">Daten werden geladen...</div>';

    // Wenn Trades bereits vorgeladen (aus Playground-Parallel-Fetch): nur Orders+Positions nachladen
    var tradesPromise = opts.tradesData
      ? Promise.resolve(opts.tradesData)
      : fetch('/api/backtest/results/' + resultId + '/trades').then(function(r) { return r.json(); });

    Promise.all([
      tradesPromise,
      fetch('/api/backtest/results/' + resultId + '/orders').then(function(r) { return r.json(); }),
      fetch('/api/backtest/results/' + resultId + '/positions').then(function(r) { return r.json(); }),
    ]).then(function(results) {
      var tradesData = results[0];
      var ordersData = results[1];
      var positionsData = results[2];
      var html = '';

      // --- Trades ---
      html += '<h6 class="mb-2">Trades (' + (tradesData.total || 0) + ')</h6>';
      if (tradesData.trades && tradesData.trades.length > 0) {
        html += '<div class="table-responsive" style="max-height:350px;overflow-y:auto;">';
        html += '<table class="table table-sm table-striped table-hover mb-4"><thead><tr>';
        html += '<th>#</th><th>Entry</th><th>Exit</th><th>Entry Preis</th><th>Exit Preis</th><th>Richtung</th><th>Size</th><th>PnL</th><th>Return %</th>';
        html += '</tr></thead><tbody>';
        tradesData.trades.forEach(function(t) {
          var pc = (t.pnl && t.pnl >= 0) ? 'val-pos' : 'val-neg';
          html += '<tr><td>' + (t.trade_idx !== undefined ? t.trade_idx : '') + '</td>';
          html += '<td class="text-nowrap">' + fmtTs(t.entry_time) + '</td>';
          html += '<td class="text-nowrap">' + fmtTs(t.exit_time) + '</td>';
          html += '<td>' + fmtNum(t.entry_price, 4) + '</td>';
          html += '<td>' + fmtNum(t.exit_price, 4) + '</td>';
          html += '<td>' + (t.direction || 'long') + '</td>';
          html += '<td>' + fmtNum(t.size, 4) + '</td>';
          html += '<td class="' + pc + '">' + fmtNum(t.pnl, 2) + '</td>';
          html += '<td class="' + pc + '">' + (t.return_pct != null ? t.return_pct.toFixed(2) + '%' : '—') + '</td></tr>';
        });
        html += '</tbody></table></div>';
      } else {
        html += '<div class="text-muted mb-4">Keine Trades vorhanden</div>';
      }

      // --- Orders ---
      html += '<h6 class="mb-2">Orders (' + (ordersData.total || 0) + ')</h6>';
      if (ordersData.orders && ordersData.orders.length > 0) {
        html += '<div class="table-responsive" style="max-height:350px;overflow-y:auto;">';
        html += '<table class="table table-sm table-striped table-hover mb-4"><thead><tr>';
        html += '<th>#</th><th>Seite</th><th>Preis</th><th>Size</th><th>Fees</th><th>Typ</th><th>Stop-Typ</th>';
        html += '</tr></thead><tbody>';
        ordersData.orders.forEach(function(o) {
          var sideLower = (o.side || '').toLowerCase();
          var sideClass = sideLower === 'buy' ? 'val-pos' : 'val-neg';
          html += '<tr><td>' + o.order_id + '</td>';
          html += '<td class="' + sideClass + '">' + o.side + '</td>';
          html += '<td>' + fmtNum(o.price, 4) + '</td>';
          html += '<td>' + fmtNum(o.size, 4) + '</td>';
          html += '<td>' + fmtNum(o.fees, 4) + '</td>';
          html += '<td>' + (o.type || '—') + '</td>';
          html += '<td>' + (o.stop_type || '—') + '</td></tr>';
        });
        html += '</tbody></table></div>';
      } else {
        html += '<div class="text-muted mb-4">Keine Orders vorhanden</div>';
      }

      // --- Positions ---
      html += '<h6 class="mb-2">Positions (' + (positionsData.total || 0) + ')</h6>';
      if (positionsData.positions && positionsData.positions.length > 0) {
        html += '<div class="table-responsive" style="max-height:350px;overflow-y:auto;">';
        html += '<table class="table table-sm table-striped table-hover mb-0"><thead><tr>';
        html += '<th>#</th><th>Entry</th><th>Exit</th><th>Avg Entry</th><th>Avg Exit</th><th>Richtung</th><th>Size</th><th>PnL</th><th>Return %</th>';
        html += '</tr></thead><tbody>';
        positionsData.positions.forEach(function(p) {
          var pc = (p.pnl != null && p.pnl >= 0) ? 'val-pos' : 'val-neg';
          html += '<tr><td>' + p.position_id + '</td>';
          html += '<td class="text-nowrap">' + fmtTs(p.entry_time) + '</td>';
          html += '<td class="text-nowrap">' + fmtTs(p.exit_time) + '</td>';
          html += '<td>' + fmtNum(p.avg_entry_price, 4) + '</td>';
          html += '<td>' + fmtNum(p.avg_exit_price, 4) + '</td>';
          html += '<td>' + (p.direction || 'Long') + '</td>';
          html += '<td>' + fmtNum(p.size, 4) + '</td>';
          html += '<td class="' + pc + '">' + fmtNum(p.pnl, 2) + '</td>';
          html += '<td class="' + pc + '">' + (p.return_pct != null ? p.return_pct.toFixed(2) + '%' : '—') + '</td></tr>';
        });
        html += '</tbody></table></div>';
      } else {
        html += '<div class="text-muted">Keine Positions vorhanden</div>';
      }

      contentEl.innerHTML = html;
    }).catch(function(err) {
      contentEl.innerHTML = '<div class="text-danger">Fehler beim Laden: ' + err.message + '</div>';
    });
  }

  // -----------------------------------------------------------------------
  // Vollanalyse-Steuerung (result_chart.html-kompatibel)
  // -----------------------------------------------------------------------

  /**
   * Startet Vollanalyse und pollt bis fertig.
   * @param {number} resultId
   * @param {Object} opts
   *   fullMetricsBarEl, extendedMetricsEl, extendedMetricsContentEl, contentEl, benchmarkValueEl
   */
  function startFullMetrics(resultId, opts) {
    opts = opts || {};
    var bar = opts.fullMetricsBarEl;
    var btn = bar ? bar.querySelector('[data-full-metrics-btn]') : null;
    if (!btn) return;

    btn.disabled = true;
    btn.className = 'btn btn-primary';
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Vollanalyse wird berechnet...';

    fetch('/api/backtest/results/' + resultId + '/full-metrics', { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.status === 'already_complete') {
          updateMetricsLevelUI('full', bar, btn);
          // Stats neu laden
          loadStatsTab(resultId, opts);
          return;
        }
        // Polling starten
        var polling = setInterval(function() {
          fetch('/api/backtest/results/' + resultId + '/metrics-level')
            .then(function(r) { return r.json(); })
            .then(function(d) {
              if (d.metrics_level === 'full') {
                clearInterval(polling);
                updateMetricsLevelUI('full', bar, btn);
                loadStatsTab(resultId, opts);
              }
            });
        }, 3000);
      })
      .catch(function() {
        btn.disabled = false;
        btn.className = 'btn btn-danger';
        btn.innerHTML = 'Fehler — nochmal versuchen';
      });
  }

  // -----------------------------------------------------------------------
  // Exports
  // -----------------------------------------------------------------------
  global.ResultTabs = {
    loadStatsTab: loadStatsTab,
    loadTradesTab: loadTradesTab,
    startFullMetrics: startFullMetrics,
  };

})(window);
