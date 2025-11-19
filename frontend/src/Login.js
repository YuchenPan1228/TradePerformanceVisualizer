import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5001/api';

const Login = ({ onLogin }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [snaptradeClientId, setSnaptradeClientId] = useState('');
  const [snaptradeConsumerKey, setSnaptradeConsumerKey] = useState('');
  const [snaptradeUserId, setSnaptradeUserId] = useState('');
  const [snaptradeUserSecret, setSnaptradeUserSecret] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Check if already logged in
    checkAuthStatus();
  }, []);

  const checkAuthStatus = async () => {
    try {
      const { data } = await axios.get(`${API_URL}/auth/status`, {
        withCredentials: true
      });
      if (data.success && data.logged_in) {
        onLogin(data.username);
      }
    } catch (err) {
      console.error('Error checking auth status:', err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isLogin) {
        // Login
        const { data } = await axios.post(
          `${API_URL}/auth/login`,
          { username, password },
          { withCredentials: true }
        );
        if (data.success) {
          onLogin(data.username);
        } else {
          setError(data.error || 'Login failed');
        }
      } else {
        // Register
        if (!snaptradeClientId || !snaptradeConsumerKey || !snaptradeUserId || !snaptradeUserSecret) {
          setError('All Snaptrade fields are required');
          setLoading(false);
          return;
        }
        const { data } = await axios.post(
          `${API_URL}/auth/register`,
          {
            username,
            password,
            snaptrade_client_id: snaptradeClientId,
            snaptrade_consumer_key: snaptradeConsumerKey,
            snaptrade_user_id: snaptradeUserId,
            snaptrade_user_secret: snaptradeUserSecret
          },
          { withCredentials: true }
        );
        if (data.success) {
          setError('');
          alert('Account created successfully! Please login.');
          setIsLogin(true);
          setSnaptradeClientId('');
          setSnaptradeConsumerKey('');
          setSnaptradeUserId('');
          setSnaptradeUserSecret('');
        } else {
          setError(data.error || 'Registration failed');
        }
      }
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            {isLogin ? 'Sign in to your account' : 'Create a new account'}
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            {isLogin ? (
              <>
                Don't have an account?{' '}
                <button
                  onClick={() => setIsLogin(false)}
                  className="font-medium text-blue-600 hover:text-blue-500"
                >
                  Register here
                </button>
              </>
            ) : (
              <>
                Already have an account?{' '}
                <button
                  onClick={() => setIsLogin(true)}
                  className="font-medium text-blue-600 hover:text-blue-500"
                >
                  Sign in here
                </button>
              </>
            )}
          </p>
        </div>
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}
          
          <div className="rounded-md shadow-sm -space-y-px">
            <div>
              <label htmlFor="username" className="sr-only">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-t-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="password" className="sr-only">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                className="appearance-none rounded-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-b-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </div>

          {!isLogin && (
            <div className="space-y-4 border-t border-gray-200 pt-4">
              <p className="text-sm text-gray-600">
                Enter your Snaptrade credentials (one-time setup):
              </p>
              <div>
                <label htmlFor="snaptrade_client_id" className="block text-sm font-medium text-gray-700 mb-1">
                  Snaptrade Client ID
                </label>
                <input
                  id="snaptrade_client_id"
                  name="snaptrade_client_id"
                  type="text"
                  required={!isLogin}
                  className="appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  placeholder="CORNELL-UNIVERSITY-RESEARCH-TEST-ICBSL"
                  value={snaptradeClientId}
                  onChange={(e) => setSnaptradeClientId(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="snaptrade_consumer_key" className="block text-sm font-medium text-gray-700 mb-1">
                  Snaptrade Consumer Key
                </label>
                <input
                  id="snaptrade_consumer_key"
                  name="snaptrade_consumer_key"
                  type="text"
                  required={!isLogin}
                  className="appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  placeholder="Your consumer key"
                  value={snaptradeConsumerKey}
                  onChange={(e) => setSnaptradeConsumerKey(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="snaptrade_user_id" className="block text-sm font-medium text-gray-700 mb-1">
                  Snaptrade User ID
                </label>
                <input
                  id="snaptrade_user_id"
                  name="snaptrade_user_id"
                  type="text"
                  required={!isLogin}
                  className="appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  placeholder="yuchen-user-1280"
                  value={snaptradeUserId}
                  onChange={(e) => setSnaptradeUserId(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="snaptrade_user_secret" className="block text-sm font-medium text-gray-700 mb-1">
                  Snaptrade User Secret
                </label>
                <input
                  id="snaptrade_user_secret"
                  name="snaptrade_user_secret"
                  type="text"
                  required={!isLogin}
                  className="appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  placeholder="Your user secret"
                  value={snaptradeUserSecret}
                  onChange={(e) => setSnaptradeUserSecret(e.target.value)}
                />
              </div>
            </div>
          )}

          <div>
            <button
              type="submit"
              disabled={loading}
              className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {loading ? 'Please wait...' : isLogin ? 'Sign in' : 'Create account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Login;

