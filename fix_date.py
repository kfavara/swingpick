import re

with open('app.py', 'r') as f:
    content = f.read()

# Update the function definition
old_def = 'def fetch_alpaca_history():'
new_def = 'def fetch_alpaca_history(start_date=None):'
content = content.replace(old_def, new_def, 1)

# Add filter logic after the loop that collects all_orders
# Find the break after collecting orders and add filter
old_break = '''            # Check if there are more pages
            if len(orders) < 100:
                break
            page_token = orders[-1].get('id')
        except:
            break
    
    # Convert to trade history'''

new_break = '''            # Check if there are more pages
            if len(orders) < 100:
                break
            page_token = orders[-1].get('id')
        except:
            break
    
    # Filter by start_date if provided
    if start_date:
        filtered_orders = []
        for order in all_orders:
            filled_at = order.get('filled_at', '')[:10]
            if filled_at >= start_date:
                filtered_orders.append(order)
        all_orders = filtered_orders
    
    # Convert to trade history'''

content = content.replace(old_break, new_break, 1)

with open('app.py', 'w') as f:
    f.write(content)
print('Done')
