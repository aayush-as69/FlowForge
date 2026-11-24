// Minimal stand-in for next/navigation so client components can render outside a Next.js app.
export const navigations = [];
export const useRouter = () => ({ push: (p) => navigations.push(["push", p]), replace: (p) => navigations.push(["replace", p]), refresh() {} });
export const usePathname = () => "/";
export const useSearchParams = () => new URLSearchParams();
export const params = {};
export const useParams = () => params;
