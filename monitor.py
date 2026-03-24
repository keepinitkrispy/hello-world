# Add debug logging for coin filtering

# Existing code above...

# After line 87, insert the following debug statement:
print(f"Bonding Curve Percentages of Filtered Coins: {[coin.bonding_curve_percentage for coin in filtered_coins]}")

# Existing code below...