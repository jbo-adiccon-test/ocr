
from dash import Dash, dcc, html, Input, Output

# Dieses Skript ist als Vorlage gedacht.
# Übernommen werden sollten:
# - CONFIG
# - df
# - get_participants
# - build_overall_ecdf_figure
# - build_group_comparison_figure
# - build_tail_figure

app = Dash(__name__)
app.title = "Latenzanalyse"

participants = get_participants(df)

app.layout = html.Div([
    html.H1("Interaktive Latenzanalyse"),
    html.Div([
        html.Label("Teilnehmer"),
        dcc.Dropdown(
            id="participant-filter",
            options=[{"label": "Alle", "value": "ALL"}] + [
                {"label": participant, "value": participant} for participant in participants
            ],
            value="ALL",
            clearable=False,
            style={"width": "320px"},
        ),
    ], style={"marginBottom": "1rem"}),

    dcc.Graph(id="fig-overall"),
    dcc.Graph(id="fig-groups"),
    dcc.Graph(id="fig-tail"),
], style={"maxWidth": "1600px", "margin": "0 auto", "padding": "1rem"})

@app.callback(
    Output("fig-overall", "figure"),
    Output("fig-groups", "figure"),
    Output("fig-tail", "figure"),
    Input("participant-filter", "value"),
)
def update_figures(selected_participant):
    if selected_participant == "ALL":
        dff = df.copy()
    else:
        dff = df[df["participant_group"] == selected_participant].copy()

    return (
        build_overall_ecdf_figure(dff, CONFIG),
        build_group_comparison_figure(df, CONFIG),
        build_tail_figure(dff if selected_participant != "ALL" else df, CONFIG),
    )

if __name__ == "__main__":
    app.run(debug=True)
