import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { ThemeProvider } from "@/lib/theme";
import Home from "@/pages/Home";
import AnalysisPage from "@/pages/Analysis";
import History from "@/pages/History";

function App() {
  return (
    <ThemeProvider>
      <div className="App">
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/analysis/:id" element={<AnalysisPage />} />
            <Route path="/history" element={<History />} />
          </Routes>
        </BrowserRouter>
        <Toaster
          richColors
          position="bottom-right"
          toastOptions={{
            style: {
              fontFamily:
                "IBM Plex Sans, ui-sans-serif, system-ui, sans-serif",
            },
          }}
        />
      </div>
    </ThemeProvider>
  );
}

export default App;
