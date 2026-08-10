-- Ranking: which products move the most units?
SELECT description,
       SUM(quantity)            AS total_qty,
       ROUND(SUM(revenue), 2)   AS total_revenue,
       COUNT(DISTINCT invoice)  AS orders
FROM sales
GROUP BY description
ORDER BY total_qty DESC
LIMIT 10;
