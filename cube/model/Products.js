cube('Products', {
  sql: `
    SELECT p.*, c.name AS category_name, c.slug AS category_slug
    FROM products p
    LEFT JOIN categories c ON c.id = p.category_id
  `,

  joins: {
    OrderItems: { sql: `${CUBE}.id = ${OrderItems}.product_id`, relationship: 'hasMany' },
  },

  measures: {
    count: { type: 'count' },
    activeCount: { type: 'count', filters: [{ sql: `${CUBE}.is_active = TRUE` }] },
    listMarginPctAvg: {
      type: 'avg',
      sql: `(price - cost) / NULLIF(price, 0)`,
      format: 'percent',
    },
  },

  dimensions: {
    id:           { sql: 'id', type: 'number', primaryKey: true },
    sku:          { sql: 'sku', type: 'string' },
    name:         { sql: 'name', type: 'string' },
    brand:        { sql: 'brand', type: 'string' },
    categoryName: { sql: 'category_name', type: 'string', title: 'Category' },
    isActive:     { sql: 'is_active', type: 'boolean' },
    launchedAt:   { sql: 'launched_at', type: 'time' },
    listPrice:    { sql: 'price', type: 'number', format: 'currency' },
  },
});
