import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import InputForm from './pages/InputForm';
import MockExam from './pages/MockExam';
import ResultReport from './pages/ResultReport';
import SingleLearning from './pages/SingleLearning';
import WrongNotes from './pages/WrongNotes';
import AdminPage from './pages/AdminPage';
import './index.css';

function App() {
  return (
    <Router>
      <div className="app-container">
        <Routes>
          <Route path="/" element={<InputForm />} />
          <Route path="/mock-exam" element={<MockExam />} />
          <Route path="/result-report" element={<ResultReport />} />
          <Route path="/single-learning" element={<SingleLearning />} />
          <Route path="/wrong-notes" element={<WrongNotes />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
