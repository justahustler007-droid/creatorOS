import React from "react";
import ReactDOM from "react-dom/client";
import "index.css";  // fixed from '@/index.css'
import "App";        // fixed from '@/App'

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
