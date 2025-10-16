// frontend/app.js

const GATEWAY_URL = '/api/telemetry';

async function runSimulation() {
    const altitude = document.getElementById('altitude').value;
    const duration = document.getElementById('duration').value;
    const outputElement = document.getElementById('output');
    
    outputElement.textContent = "Running simulation... please wait.";

    try {
        const response = await fetch(GATEWAY_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                altitude_km: altitude,
                duration_s: duration,
            }),
        });

        const data = await response.json();

        if (response.ok) {
            outputElement.textContent = JSON.stringify(data, null, 2);
        } else {
            outputElement.textContent = `Error: ${data.message || response.statusText}`;
        }
        
    } catch (error) {
        outputElement.textContent = `Network Error: Could not connect to API Gateway on ${GATEWAY_URL}. Is Docker running?`;
        console.error('Fetch error:', error);
    }
}
