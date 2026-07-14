import { useState } from "react";
import Composer from "./components/Composer";
import ResultCard from "./components/ResultCard";

export default function App() {
  const [history, setHistory] = useState([]);

  function handleResult(message, result, error) {
    setHistory((prev) => [
      { id: crypto.randomUUID(), message, result, error },
      ...prev,
    ]);
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#15171B] text-[#E8E6E1]">
      <header className="border-b border-white/10 px-6 py-4">
        <h1 className="text-lg font-semibold tracking-tight">Dashboard</h1>
      </header>

      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-6 py-8">
        <Composer onResult={handleResult} />

        <div className="flex flex-col gap-4">
          {history.length === 0 && (
            <p className="text-sm text-[#8B8F98]">
              Nothing yet — send a message above and it'll turn into knowledge-bundle updates.
            </p>
          )}
          {history.map((item) => (
            <ResultCard key={item.id} {...item} />
          ))}
        </div>
      </main>
    </div>
  );
}