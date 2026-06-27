import os
import pandas as pd


def generate_portfolio_chart(portfolio, symbol, script_dir, subplots=['trades', 'drawdowns', 'trade_pnl'], params_info=None):
    """Generate and save portfolio chart"""
    fig = portfolio.plot(subplots=subplots)
    if fig is None:
        return None

    # Layout anpassen
    fig.update_layout(
        width=1500,
        height=900,
        template="plotly_white",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.3,
            xanchor="center",
            x=0.5
        ),
        margin=dict(t=30, b=0, l=0, r=0),
        autosize=True,
    )

    # Charts-Ordner erstellen, falls nicht vorhanden
    charts_dir = os.path.join(script_dir, 'charts')
    os.makedirs(charts_dir, exist_ok=True)

    chart_type = "trading"
    file_name = f"portfolio_chart_{symbol}_{chart_type}.html"
    file_path = os.path.join(charts_dir, file_name)

    # HTML generieren
    chart_html = fig.to_html(
        include_plotlyjs='cdn',
        div_id=f"portfolio-plot-{chart_type}",
        config={
            'displayModeBar': True,
            'responsive': True,
            'toImageButtonOptions': {
                'format': 'png',
                'filename': f'portfolio_chart_{chart_type}',
                'height': 600,
                'width': 1000,
                'scale': 1
            }
        }
    )

    # Parameter-Tabelle hinzuf�gen, falls params_info �bergeben wurde
    params_html = ""
    if params_info:
        print(f"DEBUG: params_info Übergeben mit {len(params_info)} Eintr�gen")
        params_html = """
        <div style="margin: 20px; padding: 20px; background-color: #f5f5f5; border-radius: 8px; font-family: monospace;">
            <h3 style="margin-top: 0; color: #333;">Verwendete Parameter</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="background-color: #e0e0e0;">
                    <th style="padding: 8px; text-align: left; border: 1px solid #ccc;">Parameter</th>
                    <th style="padding: 8px; text-align: left; border: 1px solid #ccc;">Wert</th>
                </tr>
"""
        for key, value in params_info.items():
            params_html += f"""
                <tr>
                    <td style="padding: 8px; border: 1px solid #ccc;"><strong>{key}</strong></td>
                    <td style="padding: 8px; border: 1px solid #ccc;">{value}</td>
                </tr>
"""
        params_html += """
            </table>
        </div>
"""
        print(f"DEBUG: params_html erstellt, Länge: {len(params_html)}")
    else:
        print("DEBUG: params_info ist None oder leer!")

    # Kombiniere Chart und Parameter
    full_html = chart_html.replace('</body>', f'{params_html}</body>')
    print(f"DEBUG: full_html L�nge: {len(full_html)}, contains 'Verwendete Parameter': {'Verwendete Parameter' in full_html}")

    # HTML-Datei speichern
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(full_html)

    file_size_kb = os.path.getsize(file_path) / 1024
    print(f"Chart gespeichert: {file_path}")

    return file_path


def save_stats_to_csv(stats_sorted, symbol, script_dir, start=None, end=None, timeframe=None, exchange=None, tp_stop=None, sl_stop=None, td_stop=None, tsl_th=None, tsl_stop=None):
    """Save sorted stats to CSV file

    Args:
        stats_sorted: Sorted stats DataFrame from sort_portfolio_stats()
        symbol: Trading symbol
        script_dir: Directory to save CSV file
        start, end, timeframe, exchange: Data parameters
        tp_stop, sl_stop, td_stop, tsl_th, tsl_stop: Portfolio parameters

    Returns:
        Path to saved CSV file
    """
    # CSV-Pfad
    csv_dir = os.path.join(script_dir, 'csv')
    os.makedirs(csv_dir, exist_ok=True)
    stats_file = os.path.join(csv_dir, "optimization_results.csv")

    # Index zu Spalten machen für bessere Lesbarkeit
    stats_for_export = stats_sorted.reset_index()

    # Füge Symbol-Spalte als erste Spalte hinzu (falls noch nicht vorhanden)
    if 'symbol' not in stats_for_export.columns:
        stats_for_export.insert(0, 'symbol', symbol)
    else:
        # Symbol ist bereits vorhanden, verschiebe es an erste Stelle
        cols = ['symbol'] + [col for col in stats_for_export.columns if col != 'symbol']
        stats_for_export = stats_for_export[cols]

    # Füge Daten- und Portfolio-Parameter hinzu
    if start is not None:
        stats_for_export.insert(1, 'start', start)
    if end is not None:
        stats_for_export.insert(2, 'end', end)
    if timeframe is not None:
        stats_for_export.insert(3, 'timeframe', timeframe)
    if exchange is not None:
        stats_for_export.insert(4, 'exchange', exchange)
    if tp_stop is not None:
        stats_for_export.insert(5, 'tp_stop', tp_stop)
    if sl_stop is not None:
        stats_for_export.insert(6, 'sl_stop', sl_stop)
    if td_stop is not None:
        stats_for_export.insert(7, 'td_stop', td_stop)
    if tsl_th is not None:
        stats_for_export.insert(8, 'tsl_th', tsl_th)
    if tsl_stop is not None:
        stats_for_export.insert(9, 'tsl_stop', tsl_stop)

    # Anhängen oder neu erstellen
    if os.path.exists(stats_file):
        # Bestehende Daten laden und neue anhängen
        existing_df = pd.read_csv(stats_file)
        combined_df = pd.concat([existing_df, stats_for_export], ignore_index=True)
        combined_df.to_csv(stats_file, index=False)
        print(f"\nStats angehängt an: {stats_file}")
    else:
        # Neue Datei erstellen
        stats_for_export.to_csv(stats_file, index=False)
        print(f"\nStats exportiert nach: {stats_file}")

    return stats_file


def export_stats_to_csv(portfolios, symbol, script_dir, start=None, end=None, timeframe=None, exchange=None, tp_stop=None, sl_stop=None, td_stop=None, tsl_th=None, tsl_stop=None):
    """DEPRECATED: Use direct stats calculation and save_stats_to_csv() instead

    This is a convenience wrapper for backward compatibility.
    """
    # Berechne und sortiere Stats
    stats_df = portfolios.stats([
        'total_return',
        'sharpe_ratio',
        'win_rate',
        'max_dd',
        'total_trades'
    ], agg_func=None)
    stats_sorted = stats_df.sort_values('Total Return [%]', ascending=False)

    save_stats_to_csv(stats_sorted, symbol, script_dir, start, end, timeframe, exchange, tp_stop, sl_stop, td_stop, tsl_th, tsl_stop)
    return stats_sorted
