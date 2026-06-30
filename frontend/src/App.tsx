// App shell: routing + profile gate. NavBar is hidden on the full-screen player.

import { Route, Routes, useLocation } from 'react-router-dom';
import NavBar from './components/NavBar';
import ProfileGate from './components/ProfileGate';
import Home from './pages/Home';
import Detail from './pages/Detail';
import Player from './pages/Player';
import Search from './pages/Search';
import Stats from './pages/Stats';

export default function App() {
  const location = useLocation();
  const isPlayer = location.pathname.startsWith('/watch/');

  return (
    <ProfileGate>
      <div className="app">
        {!isPlayer && <NavBar />}
        <main className={isPlayer ? 'main-player' : 'main'}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/search" element={<Search />} />
            <Route path="/stats" element={<Stats />} />
            <Route path="/title/:kind/:id" element={<Detail />} />
            <Route path="/watch/:mediaFileId" element={<Player />} />
          </Routes>
        </main>
      </div>
    </ProfileGate>
  );
}
