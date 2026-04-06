import React, { useState, useEffect } from 'react';
import axios from 'axios';

function App() {
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const BASE_URL = "https://shiracadury-video-translator.hf.space";

  const handleUpload = async () => {
    if (!file) return alert("you forget to add a file");
    
    setLoading(true);
    setResult(null);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await axios.post(`${BASE_URL}/upload-video`, formData);
      setJobId(response.data.job_id);
      setStatus("queued");
    } catch (error) {
      console.error("Upload Error:", error);
      alert("ההעלאה נכשלה. ודאי שה-Backend רץ!");
      setLoading(false);
    }
  };

  useEffect(() => {
    let interval;
    if (jobId && (status !== "completed" && status !== "failed")) {
      interval = setInterval(async () => {
        try {
          const response = await axios.get(`${BASE_URL}/status/${jobId}`);
          setStatus(response.data.status);
          setProgress(response.data.progress);
          
          if (response.data.status === "completed") {
            setResult(response.data.result);
            setLoading(false);
            clearInterval(interval);
          }
        } catch (error) {
          console.error("Status Check Error:", error);
        }
      }, 3000); 
    }
    return () => clearInterval(interval);
  }, [jobId, status]);

  return (
    <div className="min-h-screen bg-slate-900 text-white flex flex-col items-center p-8 font-sans">
      <div className="max-w-4xl w-full bg-slate-800 p-8 rounded-2xl shadow-2xl border border-slate-700">
        
        <h1 className="text-3xl font-bold text-center mb-8 bg-gradient-to-r from-blue-400 to-emerald-400 bg-clip-text text-transparent">
          Video Translator Pro
        </h1>

        {!result && (
          <div className="space-y-6 max-w-md mx-auto">
            <div className="flex flex-col items-center justify-center border-2 border-dashed border-slate-600 rounded-lg p-6 hover:border-blue-400 transition-colors">
              <input 
                type="file" 
                onChange={(e) => setFile(e.target.files[0])} 
                className="block w-full text-sm text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-500 file:text-white hover:file:bg-blue-600 cursor-pointer"
              />
            </div>

            <button 
              onClick={handleUpload}
              disabled={loading || !file}
              className={`w-full py-3 rounded-xl font-bold text-lg transition-all ${loading ? 'bg-slate-700 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500 shadow-lg shadow-blue-900/20'}`}
            >
              {loading ? "מעבד נתונים..." : "התחל תמלול ותרגום"}
            </button>
          </div>
        )}

        {jobId && status !== "completed" && (
          <div className="mt-8 max-w-md mx-auto space-y-2">
            <div className="flex justify-between text-sm">
              <span className="capitalize">{status}...</span>
              <span>{progress}%</span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-3 overflow-hidden">
              <div className="bg-blue-500 h-full transition-all duration-500" style={{ width: `${progress}%` }}></div>
            </div>
          </div>
        )}

        {result && (
          <div className="mt-8 space-y-6 animate-in fade-in duration-700">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              
              <div className="space-y-4">
                <h2 className="text-xl font-bold text-emerald-400">תצוגה מקדימה</h2>
                <div className="relative rounded-xl overflow-hidden bg-black border border-slate-700 shadow-xl">
                  <video 
                    key={result.video_url}
                    controls 
                    className="w-full h-auto"
                  >
                    <source src={`${BASE_URL}/${result.video_url}`} type="video/mp4" />
                  </video>
                </div>
                <div className="flex gap-4">
                  <a 
                    href={`${BASE_URL}/${result.video_url}`} 
                    download
                    className="flex-1 text-center py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-semibold transition-colors"
                  >
                    הורד סרטון
                  </a>
                  <a 
                    href={`${BASE_URL}/${result.subtitles}`} 
                    download
                    className="flex-1 text-center py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-semibold transition-colors"
                  >
                    הורד כתוביות (SRT)
                  </a>
                </div>
              </div>

              <div className="space-y-4">
                <h2 className="text-xl font-bold text-blue-400">📝 סיכום הסרטון</h2>
                <div className="p-6 bg-slate-900/50 border border-slate-700 rounded-xl min-h-[200px] text-slate-300 leading-relaxed">
                  {result.summary}
                </div>
              </div>

            </div>
            
            <button 
              onClick={() => {setResult(null); setJobId(null); setFile(null); setStatus(""); setProgress(0);}}
              className="w-full py-3 mt-4 border border-slate-600 hover:bg-slate-700 rounded-xl text-slate-400 transition-all"
            >
              תרגם סרטון חדש
            </button>
          </div>
        )}

      </div>
      <p className="mt-6 text-slate-500 text-sm">Created by Shira - Software Engineer</p>
    </div>
  );
}

export default App;