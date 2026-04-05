;;; radlog.el --- RadMachine import entrypoint  -*- lexical-binding: t; -*-

(defgroup radlog nil
  "Import RadMachine activity into an Org logbook."
  :group 'tools)

(require 'json)
(require 'org-id)
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
  "Fallback Org file that accepted entries will be inserted into."
  :type '(choice (const :tag "Unset" nil) file)
  :group 'radlog)

(defcustom radlog-target-heading nil
  "Fallback heading under which accepted entries will be inserted.

If nil, append to the end of `radlog-target-file'."
  :type '(choice (const :tag "Append to end of file" nil) string)
  :group 'radlog)

(defcustom radlog-destination-map nil
  "Alist mapping entry types to insertion destinations.

Each entry is of the form:
  (ENTRY-TYPE :file \"/path/to/file.org\" :id \"ORG-ID\")"
  :type '(alist :key-type string :value-type plist)
  :group 'radlog)

(defvar radlog--candidate-queue nil)
(defvar radlog--deferred-candidates nil)

(defvar-local radlog--current-candidate nil)
(defvar-local radlog--target-file nil)
(defvar-local radlog--target-id nil)

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
    (radlog--read-date "Start date: ")
    (radlog--read-date "End date: ")
    (read-string "Username: ")))
  (let* ((target-file (or radlog-target-file
                          (read-file-name "Target Org file: " nil nil nil nil
                                          (lambda (file)
                                            (string-suffix-p ".org" file)))))
         (payload (radlog--run-cli start end user))
         (candidates (alist-get 'candidates payload)))
    (setq radlog--candidate-queue candidates)
    (setq radlog--deferred-candidates nil)
    (if (null candidates)
        (message "radlog: no candidates returned")
      (radlog--show-next-candidate target-file))))

(defun radlog-review-accept ()
  "Accept the current draft and insert it into the target Org file."
  (interactive)
  (unless radlog--current-candidate
    (user-error "No current radlog candidate"))
  (radlog--insert-entry (buffer-substring-no-properties (point-min) (point-max))
                        radlog--target-file
                        radlog--target-id
                        radlog--current-candidate)
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

(defun radlog--show-next-candidate (fallback-file)
  "Display the next candidate for review."
  (if-let* ((candidate (pop radlog--candidate-queue))
            (destination (radlog--resolve-destination candidate fallback-file))
            (buffer (get-buffer-create "*radlog-review*")))
      (let ((target-file (car destination))
            (target-id (cdr destination)))
        (with-current-buffer buffer
          (setq buffer-read-only nil)
          (erase-buffer)
          (insert (or (alist-get 'rendered_org candidate)
                      (format "%S" candidate)))
          (goto-char (point-min))
          (radlog-review-mode)
          (setq-local radlog--current-candidate candidate)
          (setq-local radlog--target-file target-file)
          (setq-local radlog--target-id target-id))
        (pop-to-buffer buffer)
        (message "radlog: C-c C-c accept, C-c C-k skip, C-c C-d defer"))
    (when-let ((buffer (get-buffer "*radlog-review*")))
      (kill-buffer buffer))
    (message "radlog complete: %d deferred" (length radlog--deferred-candidates))))

(defun radlog--advance-review (action)
  "Advance to the next candidate after ACTION."
  (let ((target-file radlog--target-file))
    (when-let ((buffer (current-buffer)))
      (kill-buffer buffer))
    (message "radlog: %s" action)
    (radlog--show-next-candidate target-file)))

(defun radlog--insert-entry (text target-file target-id candidate)
  "Insert TEXT into TARGET-FILE under TARGET-ID for CANDIDATE."
  (let ((buffer (find-file-noselect target-file)))
    (with-current-buffer buffer
      (unless (derived-mode-p 'org-mode)
        (org-mode))
      (when (radlog--duplicate-group-key-p (alist-get 'group_key candidate))
        (unless (y-or-n-p
                 (format "radlog duplicate detected for %s in %s. Insert anyway? "
                         (alist-get 'group_key candidate)
                         (abbreviate-file-name target-file)))
          (user-error "radlog insertion cancelled for duplicate %s"
                      (alist-get 'group_key candidate))))
      (save-excursion
        (radlog--goto-id target-id)
        (org-end-of-subtree t t)
        (unless (bolp)
          (insert "\n"))
        (insert text)
        (unless (string-suffix-p "\n" text)
          (insert "\n")))
      (save-buffer))))

(defun radlog--resolve-destination (candidate fallback-file)
  "Resolve insertion destination for CANDIDATE.

Return a cons cell of (FILE . ID)."
  (let* ((entry-type (alist-get 'entry_type candidate))
         (route (cdr (assoc entry-type radlog-destination-map)))
         (file (plist-get route :file))
         (id (plist-get route :id)))
    (cond
     ((and file id)
      (cons file id))
     ((and fallback-file radlog-target-heading)
      (user-error
       "radlog destination for %s must be configured with `radlog-destination-map' using :file and :id"
       entry-type))
     (t
      (user-error
       "radlog destination for %s is not configured; set `radlog-destination-map' with :file and :id"
       entry-type)))))

(defun radlog--goto-id (id)
  "Move point to the Org heading identified by ID."
  (let ((location (org-id-find id t)))
    (unless location
      (user-error "radlog could not find Org ID %s" id))
    (goto-char location)
    (org-back-to-heading t)))

(defun radlog--duplicate-group-key-p (group-key)
  "Return non-nil if GROUP-KEY already exists in the current buffer."
  (when group-key
    (save-excursion
      (goto-char (point-min))
      (re-search-forward
       (format "^:RM_GROUP_KEY: %s$" (regexp-quote group-key))
       nil
       t))))

(defun radlog--read-date (prompt)
  "Read a date with PROMPT using Org date input and return YYYY-MM-DD."
  (org-read-date nil nil nil prompt nil nil nil))

(defun radlog--project-root ()
  "Return the current radlog project root."
  (or (locate-dominating-file default-directory radlog-config-file)
      default-directory))

(provide 'radlog)

;;; radlog.el ends here
