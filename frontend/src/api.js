import axios from 'axios';

export const API_URL = '/api';

export async function apiGet(path, { params } = {}) {
  const { data } = await axios.get(`${API_URL}${path}`, { params, withCredentials: true });
  return data;
}

export async function apiPost(path, body = {}) {
  const { data } = await axios.post(`${API_URL}${path}`, body, { withCredentials: true });
  return data;
}
