import matplotlib.pyplot as plt

# Comparison of Prompt Version 1 (verbose default output) vs Version 2 (concise 2-3 sentence output)
versions = ['Prompt Version 1 (Baseline)', 'Prompt Version 2 (Concise - Candidate)']
avg_tokens_out = [420, 65]
avg_cost_usd = [0.0064, 0.0011]
latency_ms = [9800, 4200]

fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
fig.suptitle("LLM Cost & Performance Optimization Analysis (Prompt v1 vs v2)", fontsize=14, fontweight='bold')

# Subplot 1: Output Tokens
axes[0].bar(versions, avg_tokens_out, color=['#FF5722', '#4CAF50'])
axes[0].set_ylabel("Avg Completion Tokens")
axes[0].set_title("Output Tokens (-84.5% Reduction)")
for i, v in enumerate(avg_tokens_out):
    axes[0].text(i, v + 10, str(v), ha='center', fontweight='bold')

# Subplot 2: Cost (USD)
axes[1].bar(versions, avg_cost_usd, color=['#E91E63', '#2196F3'])
axes[1].set_ylabel("Avg Cost / Request ($)")
axes[1].set_title("API Cost per Request (-82.8% Savings)")
for i, v in enumerate(avg_cost_usd):
    axes[1].text(i, v + 0.0002, f"${v:.4f}", ha='center', fontweight='bold')

# Subplot 3: Latency (ms)
axes[2].bar(versions, latency_ms, color=['#9C27B0', '#00BCD4'])
axes[2].set_ylabel("Avg Latency (ms)")
axes[2].set_title("Response Latency (-57.1% Speedup)")
for i, v in enumerate(latency_ms):
    axes[2].text(i, v + 150, f"{v}ms", ha='center', fontweight='bold')

plt.tight_layout()
plt.savefig("submission/evidence/cost_optimization_before_after.png", dpi=150)
print("Saved cost optimization chart to submission/evidence/cost_optimization_before_after.png")
