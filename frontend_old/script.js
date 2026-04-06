const urlInput = document.getElementById("urlInput");
const sumBtn = document.getElementById("sumBtn");
const statusDiv = document.getElementById("status");

const summaryHe = document.getElementById("summary_he");
const summaryEn = document.getElementById("summary_en");
const downloadsDiv = document.getElementById("downloads");

const videoContainer = document.getElementById("videoContainer");
const videoPlayer = document.getElementById("videoPlayer");
const videoSource = document.getElementById("videoSource");
const subtitleTrack = document.getElementById("subtitleTrack");

sumBtn.addEventListener("click", async () => {
    const videoUrl = urlInput.value;

    if (!videoUrl || (!videoUrl.includes("youtube") && !videoUrl.includes("youtu.be"))) {
        alert("Please enter a valid YouTube link!");
        return;
    }

    sumBtn.disabled = true;

    statusDiv.innerText = "Processing video, please wait";
    summaryHe.innerText = "";
    summaryEn.innerText = "";
    downloadsDiv.innerHTML = "";
    
    videoContainer.style.display = "none"; 

    try {
        const response = await fetch("http://127.0.0.1:8000/process-video", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ url: videoUrl })
        });

        const data = await response.json();

        if (data.status === "success") {
            const server = "http://127.0.0.1:8000/";

            videoPlayer.setAttribute('crossorigin', 'anonymous');
            videoSource.src = server + data.video;
            subtitleTrack.src = server + data.subtitles_vtt;

            videoContainer.style.display = "block";

            videoPlayer.onloadedmetadata = () => {
                if (videoPlayer.textTracks.length > 0) {
                    videoPlayer.textTracks[0].mode = 'showing';
                }
            }; 

            videoPlayer.load();

            summaryHe.innerText = data.summary;
            summaryEn.innerText = "English version coming soon!";
            statusDiv.innerText = `Done in ${data.processing_time}`;

            downloadsDiv.innerHTML = `
                <h3>Downloads</h3>
                <div class="download-container">
                    <a href="${server}${data.files.hebrew_srt}" target="_blank" download>Download Hebrew Subtitles (SRT)</a>
                    <br>
                    <a href="${server}${data.files.english_srt}" target="_blank" download>Download English Subtitles (SRT)</a>
                </div>
            `;

        } else {
            statusDiv.innerText = "Error: " + (data.message || "Something went wrong");
        }

    } catch (error) {
        console.error("Communication error:", error);
        statusDiv.innerText = "Can't reach the server. Is it running?";
    }

    sumBtn.disabled = false;
});