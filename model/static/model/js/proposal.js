
document.addEventListener("DOMContentLoaded", () => {

    const proposal = document.querySelector(".model-proposal");

    if (!proposal) {
        return;
    }

    const getCsrfToken = () => {
        const cookie = document.cookie
            .split("; ")
            .find(row => row.startsWith("csrftoken="));

        return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
    };


    const postAction = async (action, changeId = null) => {

        const formData = new FormData();

        formData.append("action", action);

        if (changeId) {
            formData.append("change_id", changeId);
        }

        const response = await fetch(window.location.href, {
            method: "POST",
            headers: {
                "X-CSRFToken": getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: formData,
        });

        if (!response.ok) {
            throw new Error(`Request failed with status ${response.status}`);
        }

        return response;
    };


    const setButtonsDisabled = (disabled) => {
        proposal
            .querySelectorAll("button")
            .forEach(button => {
                button.disabled = disabled;
            });
    };


    const runAction = async (action, changeId = null) => {

        setButtonsDisabled(true);

        try {
            await postAction(action, changeId);
            window.location.reload();
        } catch (error) {
            console.error("Proposal action failed:", error);
            setButtonsDisabled(false);
            window.alert("The change could not be updated. Please try again.");
        }
    };


    proposal
        .querySelectorAll(".model-proposal-review")
        .forEach(button => {

            button.addEventListener("click", () => {
                runAction(
                    "review",
                    button.dataset.changeId
                );
            });

        });


    proposal
        .querySelectorAll(".model-proposal-unreview")
        .forEach(button => {

            button.addEventListener("click", () => {
                runAction(
                    "unreview",
                    button.dataset.changeId
                );
            });

        });


    proposal
        .querySelectorAll(".model-proposal-discard")
        .forEach(button => {

            button.addEventListener("click", () => {

                const confirmed = window.confirm(
                    "Discard this change?"
                );

                if (!confirmed) {
                    return;
                }

                runAction(
                    "discard",
                    button.dataset.changeId
                );

            });

        });


    const reviewAllButton = proposal.querySelector(
        ".model-proposal-review-all"
    );

    if (reviewAllButton) {

        reviewAllButton.addEventListener("click", () => {
            runAction("review_all");
        });

    }


    const unreviewAllButton = proposal.querySelector(
        ".model-proposal-unreview-all"
    );

    if (unreviewAllButton) {

        unreviewAllButton.addEventListener("click", () => {
            runAction("unreview_all");
        });

    }

});

