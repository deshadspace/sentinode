const express = require('express');
const axios = require('axios');
const cors = require('cors'); //Essential for front-end to call the API
const app = express();
const PORT = 3001;

// --- Configuration Constants ---
// We use localhost:5001 because the Python service is running natively on port 5001.
const PYTHON_BASE_URL = 'http://localhost:5001';
const PYTHON_SIM_URL = `${PYTHON_BASE_URL}/run-simulation`;
const DEFAULT_REALTIME_DURATION_S = 86400; // Default duration for the 'real-time' view
const DEFAULT_INCLINATION_DEG = 51.6; // Matches the Python simulator default (e.g., ISS)

// --- Utility: JSON to CSV Converter ---
function jsonToCsv(data) {
    if (!data || data.length === 0) {
        return "";
    }

    // Extract headers (keys from the first object)
    const headers = Object.keys(data[0]);
    const csvRows = [];

    // Add header row
    csvRows.push(headers.join(','));

    // Add data rows
    for (const row of data) {
        const values = headers.map(header => {
            let value = row[header];
            
            // Handle arrays (like position vectors)
            if (Array.isArray(value)) {
                value = value.map(x => (typeof x === 'number' ? x.toFixed(5) : String(x))).join('; ');
            } 
            // Handle objects (like nested status or complex JSON)
            else if (typeof value === 'object' && value !== null) {
                value = JSON.stringify(value).replace(/"/g, '""'); // Escape inner quotes
            } else {
                value = String(value);
            }
            
            // Escape values that contain quotes, commas, or newlines by wrapping in double quotes
            if (value.includes(',') || value.includes('\n') || value.includes('"')) {
                return `"${value}"`;
            }
            return value;
        });
        csvRows.push(values.join(','));
    }

    return csvRows.join('\n');
}


// --- Middleware Setup ---
// Enable CORS for all routes (to allow frontend to call this API)
app.use(cors());

// Middleware to parse incoming JSON bodies
app.use(express.json());


// --- Gateway Health Check ---
app.get('/api/status', async (req, res) => {
    // Check the Python service health using the correct localhost:5001 URL
    try {
        await axios.get(`${PYTHON_BASE_URL}/status`);
        res.json({
            status: 'up',
            service: 'Node.js API Gateway',
            python_service: 'up'
        });
    } catch (e) {
        res.status(503).json({
            status: 'degraded',
            service: 'Node.js API Gateway',
            python_service: 'down'
        });
    }
});


// --- Main Telemetry Endpoint (Real-Time Emulation) ---
// Frontend provides altitude, inclination, and local_timezone.
app.post('/api/telemetry', async (req, res) => {
    // Destructure parameters from the request body. Add inclination_deg.
    const { 
        altitude_km = 550, 
        inclination_deg = DEFAULT_INCLINATION_DEG, // NEW: Capture inclination
        duration_s = DEFAULT_REALTIME_DURATION_S, 
        local_timezone 
    } = req.body;

    console.log(`[Gateway] Real-Time Request: Alt=${altitude_km}km, Inc=${inclination_deg}deg, Duration=${duration_s}s, TZ=${local_timezone || 'N/A'}`);

    try {
        // Forward the new inclination parameter to the Python service
        const pythonResponse = await axios.post(PYTHON_SIM_URL, {
            altitude_km: parseFloat(altitude_km),
            inclination_deg: parseFloat(inclination_deg), // NEW: Pass inclination
            duration_s: parseInt(duration_s)
        });

        // Send the result from the Python service back to the client
        res.status(200).json(pythonResponse.data);

    } catch (error) {
        console.error('[Gateway] Error calling Python Service:', error.message);
        
        // Error handling logic
        const status = error.response ? error.response.status : 500;
        const message = error.response && error.response.data 
            ? error.response.data.message 
            : 'Internal server error or Python service unreachable.';

        res.status(status).json({
            status: 'error',
            message: `Simulation failed: ${message}`
        });
    }
});


// --- New: CSV Export Endpoint ---
// Takes altitude, inclination, duration, and local_timezone, returns a CSV file
app.post('/api/export-csv', async (req, res) => {
    // Destructure parameters from the request body. Add inclination_deg.
    const { 
        altitude_km, 
        inclination_deg = DEFAULT_INCLINATION_DEG, // NEW: Capture inclination
        duration_s, 
        local_timezone 
    } = req.body;

    if (!altitude_km || !duration_s) {
        return res.status(400).json({ status: 'error', message: 'Altitude and duration are required for CSV export.' });
    }

    console.log(`[Gateway] CSV Export Request: Alt=${altitude_km}km, Inc=${inclination_deg}deg, Duration=${duration_s}s, TZ=${local_timezone}`);

    try {
        // 1. Call the Python service for the full simulation duration, passing inclination
        const pythonResponse = await axios.post(PYTHON_SIM_URL, {
            altitude_km: parseFloat(altitude_km),
            inclination_deg: parseFloat(inclination_deg), // NEW: Pass inclination
            duration_s: parseInt(duration_s)
        });

        const telemetryData = pythonResponse.data.telemetry;

        // 2. Convert the JSON telemetry log to CSV format
        const csvContent = jsonToCsv(telemetryData);
        
        // 3. Set headers for file download
        const filename = `telemetry_export_${new Date().toISOString().slice(0, 10)}.csv`;
        res.setHeader('Content-Type', 'text/csv');
        res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
        
        // 4. Send the CSV content
        res.status(200).send(csvContent);

    } catch (error) {
        console.error('[Gateway] Error during CSV generation:', error.message);

        const status = error.response ? error.response.status : 500;
        const message = error.response && error.response.data 
            ? error.response.data.message 
            : 'Internal server error or Python service unreachable.';

        res.status(status).json({
            status: 'error',
            message: `CSV export failed: ${message}`
        });
    }
});


// --- Server Listen ---
app.listen(PORT, () => {
    console.log(`[Gateway] Server running on http://localhost:${PORT}`);
});
