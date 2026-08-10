-- The monthly series behind every trendline on the dashboard.
SELECT strftime('%Y-%m', invoice_date) AS month,
       description,
       SUM(quantity)                   AS qty
FROM sales
GROUP BY month, description
ORDER BY month, qty DESC;
