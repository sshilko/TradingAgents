/**
 * TradingAgents Web Interface - Main JavaScript
 */

// ===== State Management =====
const AppState = {
    activeStreams: new Map(),
    currentTaskId: null,
    isRunning: false,
    taskHistory: []
};

// ===== Initialization =====
document.addEventListener('DOMContentLoaded', () => {
    // Set default date to today
    const dateInput = document.getElementById('date');
    dateInput.valueAsDate = new Date();
    
    // Update timestamp
    updateTimestamp();
    setInterval(updateTimestamp, 60000);
    
    // Check health
    checkHealth();
    setInterval(checkHealth, 30000);
    
    console.log('TradingAgents Web Interface initialized');
});

function updateTimestamp() {
    const el = document.getElementById('timestamp');
    if (el) {
        el.textContent = new Date().toLocaleString();
    }
}

// ===== Health Check =====
async function checkHealth() {
    const indicator = document.getElementById('healthIndicator');
    if (!indicator) return;
    
    try {
        const resp = await fetch('/api/health');
        const data = await resp.json();
        
        if (data.status === 'healthy') {
            indicator.className = 'health-indicator healthy';
            indicator.title = `Healthy | Active tasks: ${data.active_tasks}`;
        } else {
            indicator.className = 'health-indicator error';
            indicator.title = 'Unhealthy';
        }
    } catch (err) {
        indicator.className = 'health-indicator error';
        indicator.title = 'Connection failed';
    }
}

// ===== Analyst Controls =====
function toggleAllAnalysts(select) {
    const checkboxes = document.querySelectorAll('.analyst-checkbox input[type="checkbox"]');
    checkboxes.forEach(cb => cb.checked = select);
}

function toggleAdvanced() {
    const panel = document.getElementById('advancedSettings');
    const icon = document.querySelector('.toggle-icon');
    
    if (panel.style.display === 'none') {
        panel.style.display = 'block';
        icon.classList.add('open');
    } else {
        panel.style.display = 'none';
        icon.classList.remove('open');
    }
}

// ===== Analysis Control =====
async function startAnalysis() {
    const ticker = document.getElementById('ticker').value.trim();
    const date = document.getElementById('date').value;
    
    if (!ticker) {
        showError('Please enter a ticker symbol');
        return;
    }
    
    if (!date) {
        showError('Please select an analysis date');
        return;
    }
    
    // Collect selected analysts
    const analysts = [];
    if (document.getElementById('a_market').checked) analysts.push('market');
    if (document.getElementById('a_social').checked) analysts.push('social');
    if (document.getElementById('a_news').checked) analysts.push('news');
    if (document.getElementById('a_fundamentals').checked) analysts.push('fundamentals');
    
    if (analysts.length === 0) {
        showError('Please select at least one analyst');
        return;
    }
    
    // Build config overrides
    const config = buildConfigOverrides();
    
    // Disable button
    const btn = document.getElementById('runBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-icon">&#128337;</span> Running...';
    AppState.isRunning = true;
    
    // Show status bar
    const statusBar = document.getElementById('statusBar');
    statusBar.style.display = 'block';
    document.getElementById('statusTitle').textContent = 'Analysis in Progress';
    document.getElementById('statusStep').textContent = '';
    document.getElementById('statusMessage').textContent = 'Starting analysis...';
    updateProgress(0);
    
    // Clear previous results
    const results = document.getElementById('results');
    results.innerHTML = '';
    
    try {
        // Submit analysis request
        const resp = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: ticker.toUpperCase(),
                date: date,
                analysts: analysts,
                config: config
            })
        });
        
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
        }
        
        const data = await resp.json();
        AppState.currentTaskId = data.task_id;
        
        // Add to task history
        AppState.taskHistory.push({
            id: data.task_id,
            ticker: ticker.toUpperCase(),
            date: date,
            startTime: new Date().toISOString()
        });
        
        updateTaskList();
        
        // Connect to SSE stream
        connectToStream(data.task_id);
        
    } catch (err) {
        console.error('Analysis submission failed:', err);
        document.getElementById('statusMessage').textContent = `Error: ${err.message}`;
        document.getElementById('statusTitle').textContent = 'Analysis Failed';
        addErrorCard(err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="btn-icon">&#9654;</span> Run Analysis';
        AppState.isRunning = false;
    }
}

function buildConfigOverrides() {
    const config = {};
    
    const provider = document.getElementById('llmProvider').value;
    if (provider) config.llm_provider = provider;
    
    const deepModel = document.getElementById('deepModel').value.trim();
    if (deepModel) config.deep_think_llm = deepModel;
    
    const quickModel = document.getElementById('quickModel').value.trim();
    if (quickModel) config.quick_think_llm = quickModel;
    
    const debateRounds = document.getElementById('debateRounds').value;
    if (debateRounds) config.max_debate_rounds = parseInt(debateRounds);
    
    return Object.keys(config).length > 0 ? config : null;
}

// ===== SSE Stream Connection =====
function connectToStream(taskId) {
    // Close any existing stream for this task
    if (AppState.activeStreams.has(taskId)) {
        AppState.activeStreams.get(taskId).close();
    }
    
    const eventSource = new EventSource(`/api/events/${taskId}`);
    AppState.activeStreams.set(taskId, eventSource);
    
    let reportCount = 0;
    
    // Handle regular messages (progress, connected)
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            handleProgressEvent(data);
        } catch (err) {
            console.warn('Failed to parse SSE message:', err);
        }
    };
    
    // Handle report events
    eventSource.addEventListener('report', function(event) {
        try {
            const data = JSON.parse(event.data);
            reportCount++;
            addReportCard(data.type, data.content, reportCount);
        } catch (err) {
            console.warn('Failed to parse report event:', err);
        }
    });
    
    // Handle decision events
    eventSource.addEventListener('decision', function(event) {
        try {
            const data = JSON.parse(event.data);
            addDecisionCard(data.content);
        } catch (err) {
            console.warn('Failed to parse decision event:', err);
        }
    });
    
    // Handle signal events
    eventSource.addEventListener('signal', function(event) {
        try {
            const data = JSON.parse(event.data);
            addSignalCard(data);
        } catch (err) {
            console.warn('Failed to parse signal event:', err);
        }
    });
    
    // Handle completion events
    eventSource.addEventListener('complete', function(event) {
        try {
            const data = JSON.parse(event.data);
            document.getElementById('statusTitle').textContent = 'Analysis Complete';
            document.getElementById('statusStep').textContent = '';
            document.getElementById('statusMessage').textContent = 
                `Finished at ${new Date(data.timestamp).toLocaleTimeString()}`;
            updateProgress(100);
            
            // Close stream
            eventSource.close();
            AppState.activeStreams.delete(taskId);
            
            // Update task list
            updateTaskList();
        } catch (err) {
            console.warn('Failed to parse complete event:', err);
        }
    });
    
    // Handle error events
    eventSource.addEventListener('error', function(event) {
        try {
            const data = JSON.parse(event.data);
            document.getElementById('statusTitle').textContent = 'Analysis Failed';
            document.getElementById('statusMessage').textContent = data.message || 'Unknown error';
            addErrorCard(data.message || 'Unknown error');
            
            eventSource.close();
            AppState.activeStreams.delete(taskId);
        } catch (parseErr) {
            // Real SSE error (connection lost)
            console.error('SSE connection error');
            document.getElementById('statusMessage').textContent = 'Connection lost';
            eventSource.close();
            AppState.activeStreams.delete(taskId);
        }
    });
    
    // Handle connection close
    eventSource.onerror = function() {
        // Don't auto-reconnect, let the event handlers deal with it
    };
}

// ===== Event Handlers =====
function handleProgressEvent(data) {
    if (data.data) {
        if (data.data.progress !== undefined) {
            updateProgress(data.data.progress);
        }
        if (data.data.step) {
            document.getElementById('statusStep').textContent = data.data.step;
        }
        if (data.data.message) {
            document.getElementById('statusMessage').textContent = data.data.message;
        }
    }
}

function updateProgress(percent) {
    const fill = document.getElementById('progressFill');
    const percentEl = document.getElementById('progressPercent');
    
    if (fill) fill.style.width = `${Math.min(100, Math.max(0, percent))}%`;
    if (percentEl) percentEl.textContent = `${Math.round(percent)}%`;
}

// ===== Result Rendering =====
function addReportCard(type, content, count) {
    const results = document.getElementById('results');
    
    const labels = {
        market_report: { title: 'Market Analysis', icon: '\ud83d\udcc8' },
        sentiment_report: { title: 'Social Media Sentiment', icon: '\ud83d\udcac' },
        news_report: { title: 'News Analysis', icon: '\ud83d\udce3' },
        fundamentals_report: { title: 'Fundamentals Analysis', icon: '\ud83d\udcca' },
        investment_plan: { title: 'Investment Plan', icon: '\ud83d\udccb' }
    };
    
    const info = labels[type] || { title: type, icon: '\ud83d\udcc4' };
    
    const card = document.createElement('div');
    card.className = 'report-card';
    card.innerHTML = `
        <div class="report-card-header">
            <span class="report-card-title">
                <span class="report-card-icon">${info.icon}</span>
                ${info.title}
            </span>
            <span class="report-card-badge">Report ${count}</span>
        </div>
        <div class="report-card-body">
            <pre>${escapeHtml(content || 'No content available')}</pre>
        </div>
    `;
    
    results.appendChild(card);
    
    // Scroll to new card
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function addDecisionCard(content) {
    const results = document.getElementById('results');
    
    const card = document.createElement('div');
    card.className = 'report-card decision';
    card.innerHTML = `
        <div class="report-card-header">
            <span class="report-card-title">
                <span class="report-card-icon">\u26a1</span>
                Final Trade Decision
            </span>
            <span class="report-card-badge" style="background: var(--accent-success);">Decision</span>
        </div>
        <div class="report-card-body">
            <pre>${escapeHtml(content || 'No decision available')}</pre>
        </div>
    `;
    
    results.appendChild(card);
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function addSignalCard(signal) {
    const results = document.getElementById('results');
    
    // Handle both dict and string signals
    let signalData = signal;
    if (typeof signal === 'string') {
        try {
            signalData = JSON.parse(signal);
        } catch (e) {
            signalData = { raw: signal };
        }
    }
    
    const action = (signalData.action || signalData.signal || 'N/A').toString().toUpperCase();
    const confidence = signalData.confidence || signalData.confidence_score || 'N/A';
    const reason = signalData.reason || signalData.reasoning || signalData.explanation || 'N/A';
    
    let actionClass = 'hold';
    if (action.includes('BUY')) actionClass = 'buy';
    else if (action.includes('SELL')) actionClass = 'sell';
    
    const card = document.createElement('div');
    card.className = 'report-card signal-card';
    card.innerHTML = `
        <div class="report-card-header">
            <span class="report-card-title">
                <span class="report-card-icon">\ud83c\udfaf</span>
                Processed Signal
            </span>
        </div>
        <div class="report-card-body">
            <div class="signal-summary">
                <div class="signal-item">
                    <label>Action</label>
                    <value class="${actionClass}">${escapeHtml(action)}</value>
                </div>
                <div class="signal-item">
                    <label>Confidence</label>
                    <value>${escapeHtml(String(confidence))}</value>
                </div>
                <div class="signal-item">
                    <label>Reasoning</label>
                    <value>${escapeHtml(String(reason))}</value>
                </div>
            </div>
        </div>
    `;
    
    results.appendChild(card);
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function addErrorCard(message) {
    const results = document.getElementById('results');
    
    const card = document.createElement('div');
    card.className = 'report-card error';
    card.innerHTML = `
        <div class="report-card-header">
            <span class="report-card-title">
                <span class="report-card-icon">\u274c</span>
                Error
            </span>
        </div>
        <div class="report-card-body">
            <pre>${escapeHtml(message)}</pre>
        </div>
    `;
    
    results.appendChild(card);
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showError(message) {
    const statusBar = document.getElementById('statusBar');
    statusBar.style.display = 'block';
    document.getElementById('statusTitle').textContent = 'Error';
    document.getElementById('statusMessage').textContent = message;
    updateProgress(0);
}

// ===== Task List =====
function updateTaskList() {
    const container = document.getElementById('activeTasks');
    const list = document.getElementById('taskList');
    
    if (AppState.taskHistory.length === 0) {
        container.style.display = 'none';
        return;
    }
    
    container.style.display = 'block';
    list.innerHTML = '';
    
    // Show last 5 tasks
    const recent = AppState.taskHistory.slice(-5).reverse();
    
    recent.forEach(task => {
        const item = document.createElement('div');
        item.className = 'task-item';
        
        const isActive = AppState.activeStreams.has(task.id);
        
        item.innerHTML = `
            <span class="ticker">${escapeHtml(task.ticker)}</span>
            <span class="status ${isActive ? 'running' : 'completed'}">
                ${isActive ? 'Running' : 'Done'}
            </span>
        `;
        
        list.appendChild(item);
    });
}

// ===== Utility Functions =====
function escapeHtml(text) {
    if (typeof text !== 'string') text = String(text);
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ===== Keyboard Shortcuts =====
document.addEventListener('keydown', (e) => {
    // Ctrl+Enter to run analysis
    if (e.ctrlKey && e.key === 'Enter') {
        e.preventDefault();
        startAnalysis();
    }
});
