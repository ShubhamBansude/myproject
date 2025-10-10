// src/components/EarnPoints.jsx

import React, { useState } from 'react';

const EarnPoints = ({ currentUser, updatePoints }) => {
    const [file, setFile] = useState(null);
    const [previewUrl, setPreviewUrl] = useState(null);
    const [loading, setLoading] = useState(false);
    const [detectionResult, setDetectionResult] = useState(null);
    const [error, setError] = useState(null);

    const handleFileChange = (event) => {
        const selectedFile = event.target.files[0];
        if (selectedFile) {
            setFile(selectedFile);
            setPreviewUrl(URL.createObjectURL(selectedFile));
            setDetectionResult(null);
            setError(null);
        }
    };

    const handleSubmit = async () => {
        if (!file) {
            alert("Please select an image first!");
            return;
        }

        const token = localStorage.getItem('authToken');
        if (!token) {
            setError('You must be logged in to earn points.');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const formData = new FormData();
            formData.append('file', file);

            const res = await fetch('http://localhost:5000/api/detect', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            const data = await res.json();
            if (!res.ok) {
                setError(data?.error || 'Detection failed.');
                setLoading(false);
                return;
            }

            const result = {
                awarded_points: data.awarded_points,
                detected_items: data.detected_items,
                recyclable_items: data.recyclable_items,
                hazardous_items: data.hazardous_items,
                duplicate: data.duplicate,
                message: data.message
            };

            setDetectionResult(result);

            if (typeof data.total_points === 'number') {
                updatePoints(data.total_points);
            }
        } catch (e) {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const isSuccess = detectionResult && detectionResult.awarded_points > 0;
    const isDetected = detectionResult && detectionResult.detected_items.length > 0;

    return (
        <div className="">
            <h3 className="text-2xl font-semibold text-gray-100 mb-6">Upload Image for Points</h3>
            
            <div className="flex flex-col md:flex-row space-y-6 md:space-y-0 md:space-x-8">
                {/* Image Upload Area */}
                <div className="flex-1">
                    <div className="rounded-xl border-2 border-dashed border-white/20 bg-white/5 hover:border-eco-green/40 transition-colors p-10 h-64 flex flex-col items-center justify-center cursor-pointer">
                        <input type="file" onChange={handleFileChange} accept="image/*" className="hidden" id="file-upload" />
                        <label htmlFor="file-upload" className="text-center">
                            <span className="text-5xl text-gray-300 mb-2 block">🖼️</span>
                            <p className="text-gray-300 font-medium">Drag & Drop or Click to Select Image</p>
                            {file && <p className="text-sm text-eco-green mt-1 font-semibold">File Selected: {file.name}</p>}
                        </label>
                    </div>

                    <button 
                        onClick={handleSubmit}
                        disabled={!file || loading}
                        className={`mt-4 w-full py-3 text-lg font-bold rounded-lg transition duration-300 ${
                            !file || loading 
                                ? 'bg-gray-500/40 text-gray-300 cursor-not-allowed' 
                                : 'bg-eco-green text-white hover:brightness-110'
                        }`}
                    >
                        {loading ? 'Analyzing...' : 'Analyze & Earn'}
                    </button>
                </div>

                {/* Results and Preview Area */}
                <div className="flex-1 bg-white/5 border border-white/10 p-4 rounded-xl shadow-inner min-h-full">
                    <h4 className="text-lg font-semibold mb-4 border-b border-white/10 pb-2 text-gray-100">Live Preview & Results</h4>
                    
                    {previewUrl && (
                        <img src={previewUrl} alt="Waste Preview" className="w-full h-48 object-contain mb-4 rounded-lg shadow-md" />
                    )}

                    {loading && (
                         <div className="flex items-center space-x-2 text-eco-green">
                             <div className="w-4 h-4 border-t-2 border-eco-green rounded-full animate-spin"></div>
                             <span>Running AI Detection...</span>
                         </div>
                    )}
                    
                    {error && (
                        <div className="p-3 mb-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded">{error}</div>
                    )}

                    {/* Feedback */}
                    {detectionResult && (
                        <div key={detectionResult.message} className={`p-4 rounded-lg ${
                            detectionResult.duplicate
                                ? 'bg-blue-500/10 border border-blue-500/20 text-blue-200'
                                : (isSuccess ? 'bg-green-500/10 border border-green-500/20 text-green-200' : (isDetected ? 'bg-yellow-500/10 border border-yellow-500/20 text-yellow-200' : 'bg-red-500/10 border border-red-500/20 text-red-200'))
                        }`}>
                            <div className="flex items-center justify-between">
                                <p className="font-bold text-lg">
                                    {detectionResult.duplicate
                                        ? 'Already Detected'
                                        : (isSuccess ? 'Waste Detected: Points Earned!' : isDetected ? 'Waste Detected: No Points' : 'Not Detected')}
                                </p>
                                {typeof detectionResult.awarded_points === 'number' && (
                                    <span className="px-3 py-1 rounded-full bg-white/10 border border-white/20 text-sm">
                                        +{detectionResult.awarded_points} pts
                                    </span>
                                )}
                            </div>
                            <p className="text-sm mt-1">{detectionResult.message}</p>

                            {/* Detected items breakdown */}
                            {(detectionResult.recyclable_items?.length || detectionResult.hazardous_items?.length) && (
                                <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                                    {detectionResult.recyclable_items?.length > 0 && (
                                        <div>
                                            <div className="text-xs uppercase tracking-wide text-gray-300 mb-1">Recyclable</div>
                                            <div className="flex flex-wrap gap-2">
                                                {detectionResult.recyclable_items.map((it, idx) => (
                                                    <span key={idx} className="px-2 py-1 rounded bg-eco-green/20 text-eco-green border border-eco-green/30 text-xs">{it}</span>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                    {detectionResult.hazardous_items?.length > 0 && (
                                        <div>
                                            <div className="text-xs uppercase tracking-wide text-gray-300 mb-1">Hazardous</div>
                                            <div className="flex flex-wrap gap-2">
                                                {detectionResult.hazardous_items.map((it, idx) => (
                                                    <span key={idx} className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 text-xs">{it}</span>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default EarnPoints;