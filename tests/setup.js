// Jest setup for jsdom environment

// Mock fetch globally
global.fetch = jest.fn();

// Helper to reset fetch mock
global.resetFetchMock = () => {
  global.fetch.mockReset();
};

// Helper to mock successful fetch response
global.mockFetchSuccess = (data, status = 200) => {
  global.fetch.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status: status,
    json: () => Promise.resolve(data)
  });
};

// Helper to mock failed fetch response
global.mockFetchError = (error) => {
  global.fetch.mockRejectedValueOnce(new Error(error));
};
