cube('OrderItems', {
  sql: `SELECT * FROM order_items`,

  joins: {
    Orders:   { sql: `${CUBE}.order_id = ${Orders}.id`,     relationship: 'belongsTo' },
    Products: { sql: `${CUBE}.product_id = ${Products}.id`, relationship: 'belongsTo' },
  },

  measures: {
    units:    { sql: 'quantity', type: 'sum' },
    revenue:  { sql: `${CUBE}.quantity * ${CUBE}.unit_price`, type: 'sum', format: 'currency' },
    cost:     { sql: `${CUBE}.quantity * ${CUBE}.unit_cost`,  type: 'sum', format: 'currency' },
    grossMargin: {
      sql: `${CUBE}.quantity * (${CUBE}.unit_price - ${CUBE}.unit_cost)`,
      type: 'sum',
      format: 'currency',
    },
    marginPct: {
      type: 'number',
      sql: `(${grossMargin} / NULLIF(${revenue}, 0))`,
      format: 'percent',
    },
  },

  dimensions: {
    id:        { sql: 'id', type: 'number', primaryKey: true },
    orderId:   { sql: 'order_id', type: 'number' },
    productId: { sql: 'product_id', type: 'number' },
  },
});
