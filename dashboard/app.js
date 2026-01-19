let chart;
let initialBalance = null;

function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
}

function initChart(data) {
    const ctx = document.getElementById('goldChart').getContext('2d');

    // Gradient for the line
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(88, 166, 255, 0.4)');
    gradient.addColorStop(1, 'rgba(88, 166, 255, 0)');

    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.history.map(h => new Date(h.timestamp * 1000).toLocaleTimeString()),
            datasets: [{
                label: 'Earned per Sale',
                data: data.history.map(h => h.amount),
                borderColor: '#58a6ff',
                backgroundColor: gradient,
                fill: true,
                tension: 0.4,
                pointRadius: 4,
                pointBackgroundColor: '#fff',
                pointBorderColor: '#58a6ff',
                borderWidth: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#8b949e', callback: value => formatCurrency(value) }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#8b949e' }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index',
            }
        }
    });
}

async function updateDashboard() {
    try {
        const response = await fetch('stats.json?t=' + Date.now());
        const data = await response.json();

        const latestSale = data.history.length > 0 ? data.history[data.history.length - 1].amount : 0;
        const totalSessionEarned = data.total_session_earned || 0;

        // Update UI
        document.getElementById('gold-per-sale').textContent = formatCurrency(latestSale);
        document.getElementById('session-total').textContent = formatCurrency(totalSessionEarned);
        document.getElementById('last-update').textContent = new Date(data.last_update * 1000).toLocaleTimeString();

        // Update Chart
        if (!chart) {
            initChart(data);
        } else {
            chart.data.labels = data.history.map(h => new Date(h.timestamp * 1000).toLocaleTimeString());
            chart.data.datasets[0].data = data.history.map(h => h.amount);
            chart.update('none'); // Update without animation for continuous feel
        }
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

// Update every 5 seconds
setInterval(updateDashboard, 5000);
updateDashboard();
