/**
 * app.js — AI Briefer
 * jQuery AJAX form submission and result rendering.
 *
 * Flow:
 *  1. User fills form + clicks Submit
 *  2. Disable button → show spinner text
 *  3. POST JSON to /api/generate/ with CSRF header
 *  4a. Success → populate result card, fade it in
 *  4b. Error   → show error banner with message
 *  5. Re-enable button regardless
 */

$(function () {

  /* -----------------------------------------------------------------------
     DOM references
  ----------------------------------------------------------------------- */
  const $form        = $('#brief-form');
  const $submitBtn   = $('#submit-btn');
  const $btnLabel    = $('#btn-label');
  const $btnSpinner  = $('#btn-spinner');
  const $errorBanner = $('#error-banner');
  const $errorMsg    = $('#error-msg');
  const $resultCard  = $('#result-card');
  const $brandDesc   = $('#brand-description');
  const $descCount   = $('#brand-desc-count');

  /* -----------------------------------------------------------------------
     Character counter for brand description
  ----------------------------------------------------------------------- */
  $brandDesc.on('input', function () {
    const len = $(this).val().length;
    $descCount.text(len + ' / 500');
    $descCount.toggleClass('near-limit', len >= 400 && len < 500);
    $descCount.toggleClass('at-limit', len >= 500);
  });

  /* -----------------------------------------------------------------------
     CSRF helper (reads the cookie Django sets)
  ----------------------------------------------------------------------- */
  function getCsrfToken() {
    const name = 'csrftoken';
    const cookies = document.cookie.split(';');
    for (let c of cookies) {
      const [k, v] = c.trim().split('=');
      if (k === name) return decodeURIComponent(v);
    }
    return '';
  }

  /* -----------------------------------------------------------------------
     UI helpers
  ----------------------------------------------------------------------- */
  function setLoading(loading) {
    if (loading) {
      $submitBtn.prop('disabled', true);
      $btnLabel.text('Generating…');
      $btnSpinner.show();
    } else {
      $submitBtn.prop('disabled', false);
      $btnLabel.text('Generate Brief');
      $btnSpinner.hide();
    }
  }

  function showError(message) {
    $errorMsg.text(message);
    $errorBanner.addClass('visible');
  }

  function clearError() {
    $errorBanner.removeClass('visible');
  }

  function showResult(data) {
    /* Hide placeholder */
    $('#result-placeholder').hide();

    /* Brief paragraph */
    $('#brief-text').text(data.brief);

    /* Content angles */
    const $angles = $('#angles-list').empty();
    $.each(data.angles, function (i, angle) {
      $angles.append(
        $('<li>').append(
          $('<span>').addClass('angle-num').text(i + 1),
          $('<span>').text(angle)
        )
      );
    });

    /* Creator criteria */
    const $criteria = $('#criteria-list').empty();
    $.each(data.criteria, function (_, criterion) {
      $criteria.append($('<li>').text(criterion));
    });

    /* Telemetry chips */
    $('#chip-latency').find('strong').text(data.latency_ms + ' ms');
    $('#chip-tokens').find('strong').text(data.total_tokens + ' tokens');
    $('#chip-prompt').find('strong').text(data.prompt_tokens);
    $('#chip-completion').find('strong').text(data.completion_tokens);

    /* Reveal with fade */
    $resultCard
      .addClass('visible')
      .css({ display: 'block', opacity: 0, transform: 'translateY(10px)' })
      .animate({ opacity: 1 }, 350);

    setTimeout(function () {
      $resultCard.css('transform', 'translateY(0)');
    }, 50);

    /* Scroll result into view on mobile */
    if (window.innerWidth < 820) {
      $('html, body').animate(
        { scrollTop: $resultCard.offset().top - 20 },
        400
      );
    }
  }

  /* -----------------------------------------------------------------------
     Form submit
  ----------------------------------------------------------------------- */
  $form.on('submit', function (e) {
    e.preventDefault();
    clearError();

    const payload = {
      brand_name:        $('#brand-name').val().trim(),
      platform:          $('#platform').val(),
      goal:              $('#goal').val(),
      tone:              $('#tone').val(),
      brand_description: $brandDesc.val().trim(),
    };

    /* Basic client-side check (server also validates) */
    if (!payload.brand_name) {
      showError('Please enter a brand name.');
      return;
    }

    setLoading(true);

    $.ajax({
      url:         '/api/generate/',
      method:      'POST',
      contentType: 'application/json',
      data:        JSON.stringify(payload),
      headers:     { 'X-CSRFToken': getCsrfToken() },

      success: function (data) {
        if (data.ok) {
          showResult(data);
        } else {
          showError(data.error || 'An unknown error occurred.');
        }
      },

      error: function (xhr) {
        let msg = 'Could not reach the server. Please try again.';
        try {
          const resp = JSON.parse(xhr.responseText);
          if (resp && resp.error) msg = resp.error;
        } catch (_) { /* keep default */ }
        showError(msg);
      },

      complete: function () {
        setLoading(false);
      },
    });
  });

});
