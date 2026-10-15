function plotVtcWithReference(analogSimData, ngspiceData)
{
    const simTrace =
    {
        x: analogSimData.vin,
        y: analogSimData.vout,
        name: 'AnalogSim (Newton-Raphson)',
        mode: 'lines',
        line:
        {
            color: 'blue'
        }
    };

    const spiceTrace =
    {
        x: ngspiceData.vin,
        y: ngspiceData.vout,
        name: 'ngspice Reference',
        mode: 'markers',
        marker:
        {
            symbol: 'circle-open',
            color: 'red'
        }
    };

    Plotly.newPlot('vtc-chart', [simTrace, spiceTrace]);
}

function main()
{
    // Fetch logic goes here, followed by calling plotVtcWithReference
}