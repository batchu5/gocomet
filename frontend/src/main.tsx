import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Link, NavLink, Route, Routes } from "react-router-dom";
import { AuctionList } from "./pages/AuctionList";
import { CreateRFQ } from "./pages/CreateRFQ";
import { AuctionDetail } from "./pages/AuctionDetail";
import "./styles.css";

function App() {
  return (
    <BrowserRouter>
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark">⇣</span> British Auction RFQ
        </Link>
        <nav>
          <NavLink to="/" end>
            Auctions
          </NavLink>
          <NavLink to="/new" className="btn btn-primary btn-sm">
            + New RFQ
          </NavLink>
        </nav>
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<AuctionList />} />
          <Route path="/new" element={<CreateRFQ />} />
          <Route path="/rfqs/:id" element={<AuctionDetail />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
