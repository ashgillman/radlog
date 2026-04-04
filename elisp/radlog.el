;;; radlog.el --- RadMachine import entrypoint  -*- lexical-binding: t; -*-

(defgroup radlog nil
  "Import RadMachine activity into an Org logbook."
  :group 'tools)

(require 'json)
(require 'org)
(require 'subr-x)

(defcustom radlog-python-command "python"
  "Python executable used to invoke the radlog CLI."
  :type 'string
  :group 'radlog)

(defcustom radlog-config-file "config.toml"
  "Config file passed to the radlog CLI."
  :type 'file
  :group 'radlog)

(defcustom radlog-target-file nil
  "Org file that accepted entries will be inserted into."
  :type '(choice (const :tag "Prompt each time" nil) file)
  :group 'radlog)

(defcustom radlog-target-heading nil
  "Heading under which accepted entries will be inserted.

If nil, append to the end of `radlog-target-file'."
  :type '(choice (const :tag "Append to end of file" nil) string)
  :group 'radlog)

(defvar radlog--candidate-queue nil)
(defvar radlog--deferred-candidates nil)

(defvar-local radlog--current-candidate nil)
(defvar-local radlog--target-file nil)
(defvar-local radlog--target-heading nil)

(define-derived-mode radlog-review-mode org-mode "Radlog-Review"
  "Major mode for reviewing imported RadMachine entries."
  (setq-local header-line-format
              "radlog review: C-c C-c accept  C-c C-k skip  C-c C-d defer"))

(define-key radlog-review-mode-map (kbd "C-c C-c") #'radlog-review-accept)
(define-key radlog-review-mode-map (kbd "C-c C-k") #'radlog-review-skip)
(define-key radlog-review-mode-map (kbd "C-c C-d") #'radlog-review-defer)

;;;###autoload
(defun radlog-import-radmachine (start end user)
  "Start a RadMachine import for START, END, and USER."
  (interactive
   (list
    (read-string "Start date (YYYY-MM-DD): ")
    (read-string "End date (YYYY-MM-DD): ")
    (read-string "Username: ")))
  (let* ((target-file (or radlog-target-file
                          (read-file-name "Target Org file: " nil nil nil nil
                                          (lambda (file)
                                            (string-suffix-p ".org" file)))))
         (target-heading radlog-target-heading)
         (payload (radlog--run-cli start end user))
         (candidates (alist-get 'candidates payload)))
    (setq radlog--candidate-queue candidates)
    (setq radlog--deferred-candidates nil)
    (if (null candidates)
        (message "radlog: no candidates returned")
      (radlog--show-next-candidate target-file target-heading))))

(defun radlog-review-accept ()
  "Accept the current draft and insert it into the target Org file."
  (interactive)
  (unless radlog--current-candidate
    (user-error "No current radlog candidate"))
  (radlog--insert-entry (buffer-substring-no-properties (point-min) (point-max))
                        radlog--target-file
                        radlog--target-heading)
  (radlog--advance-review "Accepted"))

(defun radlog-review-skip ()
  "Skip the current candidate."
  (interactive)
  (unless radlog--current-candidate
    (user-error "No current radlog candidate"))
  (radlog--advance-review "Skipped"))

(defun radlog-review-defer ()
  "Defer the current candidate for later."
  (interactive)
  (unless radlog--current-candidate
    (user-error "No current radlog candidate"))
  (push radlog--current-candidate radlog--deferred-candidates)
  (radlog--advance-review "Deferred"))

(defun radlog--run-cli (start end user)
  "Run the radlog CLI for START, END, and USER and return parsed JSON."
  (let* ((default-directory (radlog--project-root))
         (args (list "-m" "radlog.cli"
                     "--config" (expand-file-name radlog-config-file default-directory)
                     "--collect" "qa-candidates"
                     "--start" start
                     "--end" end
                     "--user" user))
         (stdout (generate-new-buffer " *radlog-stdout*"))
         (stderr-file (make-temp-file "radlog-stderr-")))
    (unwind-protect
        (let ((status (apply #'call-process radlog-python-command nil (list stdout stderr-file) nil args)))
          (unless (eq status 0)
            (with-temp-buffer
              (insert-file-contents stderr-file)
              (error "radlog CLI failed: %s" (string-trim (buffer-string)))))
          (with-current-buffer stdout
            (json-parse-string (buffer-string)
                               :object-type 'alist
                               :array-type 'list
                               :null-object nil
                               :false-object nil)))
      (kill-buffer stdout)
      (ignore-errors (delete-file stderr-file)))))

(defun radlog--show-next-candidate (target-file target-heading)
  "Display the next candidate for review."
  (if-let ((candidate (pop radlog--candidate-queue)))
      (let ((buffer (get-buffer-create "*radlog-review*")))
        (with-current-buffer buffer
          (setq buffer-read-only nil)
          (erase-buffer)
          (insert (or (alist-get 'rendered_org candidate)
                      (format "%S" candidate)))
          (goto-char (point-min))
          (radlog-review-mode)
          (setq-local radlog--current-candidate candidate)
          (setq-local radlog--target-file target-file)
          (setq-local radlog--target-heading target-heading))
        (pop-to-buffer buffer)
        (message "radlog: C-c C-c accept, C-c C-k skip, C-c C-d defer"))
    (when-let ((buffer (get-buffer "*radlog-review*")))
      (kill-buffer buffer))
    (message "radlog complete: %d deferred" (length radlog--deferred-candidates))))

(defun radlog--advance-review (action)
  "Advance to the next candidate after ACTION."
  (let ((target-file radlog--target-file)
        (target-heading radlog--target-heading))
    (when-let ((buffer (current-buffer)))
      (kill-buffer buffer))
    (message "radlog: %s" action)
    (radlog--show-next-candidate target-file target-heading)))

(defun radlog--insert-entry (text target-file target-heading)
  "Insert TEXT into TARGET-FILE, optionally under TARGET-HEADING."
  (let ((buffer (find-file-noselect target-file)))
    (with-current-buffer buffer
      (unless (derived-mode-p 'org-mode)
        (org-mode))
      (save-excursion
        (goto-char (point-min))
        (if target-heading
            (radlog--goto-or-create-heading target-heading)
          (goto-char (point-max)))
        (unless (bolp)
          (insert "\n"))
        (insert text)
        (unless (string-suffix-p "\n" text)
          (insert "\n")))
      (save-buffer))
    (pop-to-buffer buffer)))

(defun radlog--goto-or-create-heading (heading)
  "Move point to the end of HEADING, creating it if needed."
  (goto-char (point-min))
  (if (re-search-forward (format "^\\*+ %s$" (regexp-quote heading)) nil t)
      (org-end-of-subtree t t)
    (goto-char (point-max))
    (unless (bolp)
      (insert "\n"))
    (insert "* " heading "\n")
    (point-max)))

(defun radlog--project-root ()
  "Return the current radlog project root."
  (or (locate-dominating-file default-directory radlog-config-file)
      default-directory))

(provide 'radlog)

;;; radlog.el ends here
