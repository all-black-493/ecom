cube('Orders', {
  sql: `
    SELECT *
    FROM orders
    WHERE status NOT IN ('cancelled')
  `,

  joins: {
    Customers:    { sql: `${CUBE}.customer_id = ${Customers}.id`, relationship: 'belongsTo' },
    OrderItems:   { sql: `${CUBE}.id = ${OrderItems}.order_id`,   relationship: 'hasMany' },
  },

  measures: {
    count:    { type: 'count' },
    revenue:  { sql: 'grand_total', type: 'sum', format: 'currency' },
    aov:      { sql: 'grand_total', type: 'avg',  format: 'currency' },
    discount: { sql: 'discount_total', type: 'sum', format: 'currency' },
    uniqueCustomers: { sql: 'customer_id', type: 'countDistinct' },
    repeatPurchaseRate: {
      type: 'number',
      sql: `
        ${uniqueCustomers} -
        (SELECT COUNT(*) FROM (
            SELECT customer_id FROM ${CUBE} GROUP BY 1 HAVING COUNT(*) = 1
        ) s)
      `,
      format: 'percent',
    },
  },

  dimensions: {
    id:           { sql: 'id', type: 'number', primaryKey: true },
    orderNumber:  { sql: 'order_number', type: 'string' },
    status:       { sql: 'status', type: 'string' },
    channel:      { sql: 'channel', type: 'string' },
    deviceType:   { sql: 'device_type', type: 'string' },
    utmSource:    { sql: 'utm_source', type: 'string' },
    placedAt:     { sql: 'placed_at', type: 'time' },
    deliveredAt:  { sql: 'delivered_at', type: 'time' },
  },

  preAggregations: {
    dailyRevenue: {
      measures: [count, revenue, aov, uniqueCustomers],
      dimensions: [channel, deviceType],
      timeDimension: placedAt,
      granularity: 'day',
      refreshKey: { every: '1 hour' },
    },
  },
});
