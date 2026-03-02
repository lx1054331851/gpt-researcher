interface GetHostParams {
  purpose?: string;
}

const LOCAL_HOSTNAMES = new Set([
  "localhost",
  "127.0.0.1",
  "0.0.0.0",
  "::1",
  "[::1]",
]);

const isLocalHostname = (hostname: string): boolean =>
  LOCAL_HOSTNAMES.has(hostname) || hostname.startsWith("127.");

export const getHost = ({ purpose }: GetHostParams = {}): string => {
  if (typeof window !== 'undefined') {
    const { host, hostname } = window.location;
    const apiUrlInLocalStorage = localStorage.getItem("GPTR_API_URL");
    
    const urlParams = new URLSearchParams(window.location.search);
    const apiUrlInUrlParams = urlParams.get("GPTR_API_URL");
    
    if (apiUrlInLocalStorage) {
      return apiUrlInLocalStorage;
    } else if (apiUrlInUrlParams) {
      return apiUrlInUrlParams;
    } else if (process.env.NEXT_PUBLIC_GPTR_API_URL) {
      return process.env.NEXT_PUBLIC_GPTR_API_URL;
    } else if (process.env.REACT_APP_GPTR_API_URL) {
      return process.env.REACT_APP_GPTR_API_URL;
    } else if (purpose === 'langgraph-gui') {
      return isLocalHostname(hostname) ? 'http%3A%2F%2F127.0.0.1%3A8123' : `https://${host}`;
    } else {
      return isLocalHostname(hostname) ? 'http://localhost:8000' : `https://${host}`;
    }
  }
  return '';
};
