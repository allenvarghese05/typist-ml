import { API_BASE } from "../api/paths";

/** Milestone 0 placeholder page. Replaced by the real screens from T1.5 on. */
export function App() {
  return (
    <main className="mx-auto max-w-2xl p-8 font-sans">
      <h1 className="text-2xl font-semibold">Typist-ML</h1>
      <p className="mt-4 text-gray-700">
        Milestone 0 scaffold. The API is reached through <code>{API_BASE}</code>.
      </p>
    </main>
  );
}
