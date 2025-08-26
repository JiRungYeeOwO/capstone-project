document.getElementById("submit-btn").addEventListener("click", function() {
    var comment = document.getElementById("comment-input").value;
    if (comment.trim() !== "") {
        var form = document.getElementById("comment-form");
        var formData = new FormData(form);
        fetch('/add_comment', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                alert(data.error); // '로그인이 필요합니다.' 메시지 표시
                window.location.href = '/login'; // 로그인 페이지로 리다이렉트
            } else {
                // 페이지 새로고침
                location.reload();
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
    }
});
