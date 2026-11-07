"""Dash UI for inspecting raw RTL-SDR channel health."""
from collections import deque
import time

COLORS = ("#7ccc63", "#f39c12", "#e74c3c", "#3498db", "#9b59b6")
STATUS_COLORS = {"DATA OK": "#7ccc63", "SLOW": "#f39c12", "NO DATA": "#e74c3c"}


def create_layout(freq=433.0, gain=280, rate=2_400_000):
    from dash import dcc, html
    return html.Div([
        dcc.Interval(id="refresh", interval=500, n_intervals=0),
        html.Header(html.H1("KrakenSDR Raw Data Viewer")),
        html.Div(id="device-summary", className="device-summary"),
        html.Div(id="channel-cards", className="channel-grid"),
        html.Div([dcc.Graph(id="spectrum", config={"displayModeBar": False}), dcc.Graph(id="power-trend", config={"displayModeBar": False})], className="plots"),
        html.Section([html.H2("Receiver controls"), dcc.Input(id="freq", type="number", value=freq, step=.1),
                      dcc.Dropdown(id="gain", options=[], value=gain, clearable=False),
                      dcc.Dropdown(id="rate", options=[{"label": f"{x / 1e6:g} MS/s", "value": x} for x in (1_024_000, 2_048_000, 2_400_000)], value=rate, clearable=False),
                      html.Button("Apply", id="apply", className="btn"), html.Span(id="apply-result")], className="card controls"),
    ])


def build_spectrum_figure(states):
    import plotly.graph_objects as go
    fig = go.Figure()
    for i, row in enumerate(states):
        values = row["spectrum"]
        n = len(values)
        rate = row["sample_rate"]
        freq = row["center_freq"]
        x = [(freq + ((k - n / 2) * rate / n)) / 1e6 for k in range(n)]
        fig.add_trace(go.Scatter(x=x, y=values, mode="lines", name=row["serial"], line={"color": COLORS[i % len(COLORS)]}))
    fig.update_layout(template="plotly_dark", uirevision="kraken-spectrum", title="Live spectrum", xaxis_title="Frequency (MHz)", yaxis_title="Power (dBFS)",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def build_trend_figure(states):
    import plotly.graph_objects as go
    fig = go.Figure()
    for i, row in enumerate(states):
        history = row["history"][-120:]
        if history:
            now = time.time()
            fig.add_trace(go.Scatter(x=[x[0] - now for x in history], y=[x[1] for x in history], mode="lines", name=row["serial"], line={"color": COLORS[i % len(COLORS)]}))
    fig.update_layout(template="plotly_dark", uirevision="kraken-trend", title="Power trend (last 60 s)", xaxis_title="Seconds ago", yaxis_title="Power (dBFS)", xaxis={"range": [-60, 0]},
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def create_app(readers, device_count=None, freq=433.0, gain=280, rate=2_400_000):
    from dash import Dash, Input, Output, State, html, no_update
    app = Dash(__name__)
    app.layout = create_layout(freq, gain, rate)
    gain_steps = next((getattr(reader, "gain_options", None) for reader in readers if getattr(reader, "gain_options", None)), None)
    if gain_steps:
        from dash import dcc
        def find(node):
            if isinstance(node, (list, tuple)):
                for child in node:
                    found = find(child)
                    if found is not None: return found
            elif getattr(node, "id", None) == "gain": return node
            elif hasattr(node, "children"): return find(node.children)
        gain_dropdown = find(app.layout)
        gain_dropdown.options = [{"label": f"{x / 10:.1f} dB", "value": x} for x in gain_steps]
    app.kraken_readers = readers
    app.kraken_refresh = None

    @app.callback(Output("device-summary", "children"), Output("channel-cards", "children"),
                  Output("spectrum", "figure"), Output("power-trend", "figure"), Input("refresh", "n_intervals"))
    def refresh(_):
        states = [r.snapshot() for r in readers]
        cards = []
        for row in states:
            status = row["status"]
            cards.append(html.Section([
                html.H2(f"Channel {row['index']} · {row['serial']}"),
                html.Div(status, className="status", style={"color": STATUS_COLORS[status]}),
                html.Div(f"{row['product']} · {row['center_freq'] / 1e6:.3f} MHz"),
                html.Div(f"Samples/s: {row['sps']:,.0f} / {row['sample_rate']:,.0f}"),
                html.Div(f"Power: {row['power_dbfs']:.1f} dBFS · clip: {100 * row['clip_fraction']:.3f}%"),
                html.Div(f"DC: {row['dc_offset'].real:+.4f} {row['dc_offset'].imag:+.4f}j · read errors: {row['read_errors']}"),
                html.Div(row["error"] or "", style={"color": STATUS_COLORS["NO DATA"]}),
            ], className="card channel-card", **{"data-channel": row["index"], "data-status": status}))
        found = device_count if device_count is not None else len(readers)
        summary = (html.Div("No KrakenSDR found (0 devices with USB ID 0bda:2838). Check the 5 V supply, the USB cable, and run lsusb.",
                             style={"color": "#e74c3c", "fontSize": "2rem", "fontWeight": "bold"}) if found == 0 else
                   html.Div(f"{found} devices found · USB ID 0bda:2838"))
        result = (summary, cards, build_spectrum_figure(states), build_trend_figure(states))
        app.kraken_refresh = refresh
        return result

    @app.callback(Output("apply-result", "children"), Input("apply", "n_clicks"), State("freq", "value"), State("gain", "value"), State("rate", "value"), prevent_initial_call=True)
    def apply_settings(_clicks, freq, gain, rate):
        if freq is None or freq <= 0 or gain is None or rate is None:
            return "Enter valid frequency, gain, and sample rate."
        for reader in readers:
            reader.retune(center_freq=int(float(freq) * 1e6), gain=int(gain), sample_rate=int(rate))
        return "Settings applied."

    # Dash registers decorated functions in callback_map; expose the callable for headless tests.
    app.kraken_refresh = refresh
    app.kraken_apply = apply_settings
    return app


def run_app(readers, device_count=None, port=8090):
    app = create_app(readers, device_count)
    app.run(host="127.0.0.1", port=port, debug=False)
