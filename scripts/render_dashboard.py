import json
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

logs = []
with open("data/logs.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            logs.append(json.loads(line))

df = pd.DataFrame(logs)

fig, axes = plt.subplots(3, 2, figsize=(14, 12))
fig.suptitle("Day 13 AI Observability - Runtime Dashboard (6 Panels Contract)", fontsize=16, fontweight='bold')

# Panel 1: Latency percentiles
ax1 = axes[0, 0]
response_sent_df = df[df['event'] == 'response_sent'] if 'event' in df.columns else pd.DataFrame()
if not response_sent_df.empty and 'latency_ms' in response_sent_df.columns:
    latencies = response_sent_df['latency_ms'].dropna()
    p50 = np.percentile(latencies, 50)
    p95 = np.percentile(latencies, 95)
    p99 = np.percentile(latencies, 99)
    ax1.bar(['P50', 'P95', 'P99'], [p50, p95, p99], color=['#4CAF50', '#FF9800', '#F44336'])
    ax1.axhline(3000, color='red', linestyle='--', label='Threshold (LTE 3000ms)')
    ax1.set_ylabel("Latency (ms)")
    ax1.set_title("Latency Percentiles (ms)")
    ax1.legend()
else:
    ax1.text(0.5, 0.5, "No Latency Data", ha='center')

# Panel 2: Request Traffic
ax2 = axes[0, 1]
if 'event' in df.columns:
    traffic_cnt = (df['event'] == 'request_received').sum()
    ax2.bar(['Total Requests'], [traffic_cnt], color='#2196F3')
    ax2.axhline(1, color='green', linestyle='--', label='Threshold (GTE 1 req/min)')
    ax2.set_ylabel("Count")
    ax2.set_title("Request Traffic (requests_per_minute)")
    ax2.legend()

# Panel 3: Error Rate & Breakdown
ax3 = axes[1, 0]
if 'event' in df.columns:
    total_req = (df['event'] == 'request_received').sum()
    failed_req = (df['event'] == 'request_failed').sum()
    err_rate = (failed_req / total_req * 100) if total_req > 0 else 0
    ax3.bar(['Error Rate (%)'], [err_rate], color='#E91E63')
    ax3.axhline(2, color='red', linestyle='--', label='Threshold (LTE 2%)')
    ax3.set_ylabel("Percent (%)")
    ax3.set_title("Error Rate and Breakdown (%)")
    ax3.legend()

# Panel 4: Cost Over Time
ax4 = axes[1, 1]
if not response_sent_df.empty and 'cost_usd' in response_sent_df.columns:
    total_cost = response_sent_df['cost_usd'].sum()
    ax4.bar(['Total Cost (USD)'], [total_cost], color='#9C27B0')
    ax4.axhline(2.5, color='red', linestyle='--', label='Threshold (LTE $2.5)')
    ax4.set_ylabel("USD ($)")
    ax4.set_title("Cost Over Time (USD)")
    ax4.legend()

# Panel 5: Input & Output Tokens
ax5 = axes[2, 0]
if not response_sent_df.empty and 'tokens_in' in response_sent_df.columns and 'tokens_out' in response_sent_df.columns:
    sum_in = response_sent_df['tokens_in'].sum()
    sum_out = response_sent_df['tokens_out'].sum()
    ax5.bar(['Tokens In', 'Tokens Out'], [sum_in, sum_out], color=['#00BCD4', '#3F51B5'])
    ax5.axhline(50000, color='red', linestyle='--', label='Threshold (LTE 50000 tokens)')
    ax5.set_ylabel("Tokens")
    ax5.set_title("Input and Output Tokens")
    ax5.legend()

# Panel 6: Quality Proxy
ax6 = axes[2, 1]
if not response_sent_df.empty and 'quality_score' in response_sent_df.columns:
    mean_quality = response_sent_df['quality_score'].mean()
    ax6.bar(['Mean Quality'], [mean_quality], color='#8BC34A')
    ax6.axhline(0.75, color='green', linestyle='--', label='Threshold (GTE 0.75 score)')
    ax6.set_ylim(0, 1.0)
    ax6.set_ylabel("Score (0 to 1)")
    ax6.set_title("Quality Proxy (Mean Score)")
    ax6.legend()

plt.tight_layout()
plt.savefig("submission/evidence/dashboard_runtime.png", dpi=150)
print("Dashboard saved to submission/evidence/dashboard_runtime.png")
