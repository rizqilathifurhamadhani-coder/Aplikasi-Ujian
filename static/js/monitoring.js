console.log("Monitoring aktif");

const videos = document.querySelectorAll("video");

videos.forEach(video => {

    video.addEventListener("loadeddata", () => {

        console.log(
            "Video aktif:",
            video.id
        );

    });

});
