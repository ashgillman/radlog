(require 'ert)
(require 'cl-lib)

(defconst radlog-test-project-root
  (file-name-directory
   (directory-file-name
    (file-name-directory (or load-file-name buffer-file-name)))))

(load-file (expand-file-name "elisp/radlog.el" radlog-test-project-root))

(ert-deftest radlog-project-root-is-independent-of-default-directory ()
  (let ((default-directory temporary-file-directory))
    (should
     (equal
      (file-truename (radlog--project-root))
      (file-truename radlog-test-project-root)))))

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

(ert-deftest radlog-adjust-heading-level-makes-draft-a-child-of-target ()
  (should
   (equal
    (radlog--adjust-heading-level
     "**** [2026-04-07 Tue] ABC Weekly :ABCWeekly:\nBody"
     5)
    "***** [2026-04-07 Tue] ABC Weekly :ABCWeekly:\nBody")))

(ert-deftest radlog-skip-future-like-candidates-removes-same-entry-type-when-confirmed ()
  (let ((radlog--candidate-queue
         '(((entry_type . "abc_weekly") (title . "ABC Weekly") (group_key . "week-2"))
           ((entry_type . "linac_mqc") (title . "LAx MQC") (group_key . "mqc"))
           ((entry_type . "abc_weekly") (title . "ABC Weekly") (group_key . "week-3")))))
    (cl-letf (((symbol-function 'y-or-n-p) (lambda (_) t)))
      (should
       (equal
        (radlog--maybe-skip-future-like-candidates
         '((entry_type . "abc_weekly") (title . "ABC Weekly") (group_key . "week-1")))
        2))
      (should
       (equal
        radlog--candidate-queue
        '(((entry_type . "linac_mqc") (title . "LAx MQC") (group_key . "mqc"))))))))

(ert-deftest radlog-skip-future-like-candidates-keeps-queue-when-declined ()
  (let ((radlog--candidate-queue
         '(((entry_type . "abc_weekly") (title . "ABC Weekly") (group_key . "week-2")))))
    (cl-letf (((symbol-function 'y-or-n-p) (lambda (_) nil)))
      (should
       (= (radlog--maybe-skip-future-like-candidates
           '((entry_type . "abc_weekly") (title . "ABC Weekly") (group_key . "week-1")))
          0))
      (should
       (equal
        radlog--candidate-queue
        '(((entry_type . "abc_weekly") (title . "ABC Weekly") (group_key . "week-2"))))))))
