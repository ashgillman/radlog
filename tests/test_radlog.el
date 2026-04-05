(require 'ert)
(load-file "/Users/gil/src/radmachine-to-logbook/elisp/radlog.el")

(ert-deftest radlog-resolve-destination-uses-entry-type-route ()
  (let ((radlog-destination-map '(("linac_mqc" :file "/tmp/logbook.org" :id "abc123"))))
    (should
     (equal
      (radlog--resolve-destination '((entry_type . "linac_mqc")) nil)
      '("/tmp/logbook.org" . "abc123")))))

(ert-deftest radlog-resolve-destination-falls-back-to-default-route ()
  (let ((radlog-destination-map '(("default" :file "/tmp/logbook.org" :id "fallback"))))
    (should
     (equal
      (radlog--resolve-destination '((entry_type . "qa_session")) nil)
      '("/tmp/logbook.org" . "fallback")))))

(ert-deftest radlog-resolve-destination-errors-without-route ()
  (let ((radlog-destination-map nil))
    (should-error
     (radlog--resolve-destination '((entry_type . "qa_session")) nil)
     :type 'user-error)))
