import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

export const api = {
  meta: () => http.get('/meta/columns'),

  list: (resource, params) => http.get(`/${resource}`, { params }),
  all: (resource, params) => http.get(`/${resource}/all`, { params }),
  create: (resource, data) => http.post(`/${resource}`, data),
  update: (resource, id, data) => http.put(`/${resource}/${id}`, data),
  remove: (resource, id) => http.delete(`/${resource}/${id}`),
  removeMany: (resource, ids) =>
    http.delete(`/${resource}`, { params: { ids: ids.join(',') } }),

  exportUrl: (resource, format, keyword) => {
    const q = new URLSearchParams({ format })
    if (keyword) q.set('keyword', keyword)
    return `/api/export/${resource}?${q.toString()}`
  },
  templateUrl: (resource) => `/api/import/template/${resource}`,
  import: (resource, file, replace = true) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post(`/import/${resource}`, fd, { params: { replace } })
  },
  batchImport: (batchId, target, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post(`/batches/${batchId}/import`, fd, { params: { target } })
  },
}