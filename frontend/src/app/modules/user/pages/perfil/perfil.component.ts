import { Component, inject, signal, WritableSignal, OnInit } from '@angular/core';
import { FormBuilder, Validators, ReactiveFormsModule, FormControl, FormArray, FormGroup } from '@angular/forms';
import { NavBarComponent } from '../../components/nav-bar/nav-bar.component';
import { CommonModule, formatDate } from '@angular/common';
import { ModalComponent } from '../../components/modal/modal.component';
import { ResponseModalComponent } from '../../../views/response-modal/response-modal.component';
import { ModalConfig } from '../../../../shared/interfaces/common.interfaces';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../../../../core/services/auth.service';
import { DateUtils } from '../../../../core/utils/date-utils';
import { FileUtils } from '../../../../core/utils/file-utils';
import { UserProfile, ProfileFormData } from '../../../../core/models/model';
import { CATEGORIES } from '../../../../core/constants/categories';
import { environment } from '../../../../../environments/environment.prod';

@Component({
  selector: 'app-perfil',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    NavBarComponent,
    CommonModule,
    ModalComponent,
    ResponseModalComponent
  ],
  templateUrl: './perfil.component.html',
  styleUrls: ['./perfil.component.css']
})
export class PerfilComponent implements OnInit {

  userProfile = signal<UserProfile | null>(null);
  imageUser = signal<string | null>(null);
  loading = signal(false);
  error = signal<string | null>(null);
  submittedForm = signal(false);
  hideNav = signal(true);
  showModal = false;
  textModal =""

  readonly categories = CATEGORIES;

  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly dateUtils = inject(DateUtils);
  private readonly fileUtils = inject(FileUtils);

  protected profileForm = this.fb.group({
    firstName: ['', [Validators.required, Validators.minLength(2)]],
    lastName: ['', Validators.required],
    birthDate: ['', this.dateValidator],
    categories: this.buildCategoriesFormArray()
  });

  responseModalConfig: ModalConfig = {
    message: '',
    type: 'info',
    confirmText: 'OK',
    showCancel: false
  };
  responseModalVisible: boolean = false;

  constructor() {
    this.route.data.subscribe(data => {
      this.hideNav.set(data['hideNav'] || false);
    });
  }

  ngOnInit(): void {
    this.loadUserProfileData();
  }



  loadUserProfileData(): void {
    this.loading.set(true);
    this.error.set(null);

    this.authService.getUser().subscribe({
      next: (response) => {
        if (response) {
          const { data } = response;
          this.userProfile.set({ ...data, categorias: data.categories });
          
          this.authService.getUserProfile().subscribe({
            next: (socialResponse) => {
              if (socialResponse) {
                const socialData = this.normalizeProfileData(socialResponse);
                this.userProfile.update(profile => ({
                  ...profile!,
                  provedores: socialData.provedores
                }));
                this.updateFormWithProfileData();
              }
              this.loading.set(false);
            },
            error: (err) => {
              console.error(err);
              this.updateFormWithProfileData();
              this.loading.set(false);
            }
          });
        } else {
          this.authService.getUserProfile().subscribe({
            next: (response) => {
              console.log(response);
              if (response) {
                this.userProfile.set(this.normalizeProfileData(response));
                this.updateFormWithProfileData();
              }
              this.loading.set(false);
            },
            error: (err) => {
              console.error(err);
              this.error.set(err.error?.message || err.message);
              this.loading.set(false);
            }
          });
        }
      },
      error: (err) => {
        console.error(err);
        this.error.set(err.error?.message || err.message);
        this.loading.set(false);
      }
    })

    
  }

  private normalizeProfileData(response: any): UserProfile {
    if (Array.isArray(response) && response.length === 2 && response[0] === 200) {
      return response[1];
    } else if (response?.status === 200) {
      return response.dados || response;
    }
    return response;
  }

  private updateFormWithProfileData(): void {
    const profile = this.userProfile();
    if (!profile) return;
    
    const { firstName, lastName } = this.extractNameInfo(profile);
  
    this.profileForm.patchValue({
      firstName,
      lastName,
      birthDate: this.dateUtils.formatToLocalDate(profile.data_nasc)
    });

    this.updateProfileImage(profile);
    this.updateSelectedCategories(profile.categorias || []);
  }

  private extractNameInfo(profile: UserProfile): { firstName: string, lastName: string } {
    let firstName = '';
    let lastName = '';

    if (profile.provedores) {
      if (profile.provedores['linkedin-server']) {
        const linkedinData = profile.provedores['linkedin-server'] as any;
        
        if (linkedinData.perfil_linkedin) {
          firstName = linkedinData.perfil_linkedin.given_name || '';
          lastName = linkedinData.perfil_linkedin.family_name || '';
        }
        
        if (!firstName) {
          firstName = linkedinData.given_name || '';
          lastName = linkedinData.family_name || '';
        }
      } else if (profile.provedores['google']) {
        firstName = profile.provedores['google'].given_name || '';
        if (profile.provedores['google'].name &&
          profile.provedores['google'].name !== firstName) {
          const nameParts = profile.provedores['google'].name.split(' ');
          if (nameParts.length > 1) {
            lastName = nameParts.slice(1).join(' ');
          }
        }
      }
    }

    if (profile.first_name && profile.last_name && 
        profile.first_name !== '-' && profile.last_name !== '-') {
      firstName = profile.first_name;
      lastName = profile.last_name;
    }

    if (!firstName && profile.username) {
      firstName = profile.username;
    }

    return { firstName, lastName };
  }

  private updateProfileImage(profile: UserProfile): void {
    if (profile.provedores) {
      if (profile.provedores['linkedin-server']?.url_imagem_perfil) {
        this.imageUser.set(profile.provedores['linkedin-server'].url_imagem_perfil);
      } else if (profile.provedores['google']?.picture) {
        this.imageUser.set(profile.provedores['google'].picture);
      }
    }

    if( profile.profile_picture ) 
      this.imageUser.set( `${environment.getBaseUrl()}/media/${profile.profile_picture}`)
    
    if( profile.profile_picture_url ) 
      this.imageUser.set(  profile.profile_picture_url)
  }

  private updateSelectedCategories(selectedCategories: string[]): void {
    const categoriesArray = this.profileForm.get('categories') as FormArray;
    categoriesArray.clear();
    this.categories.forEach(category => {
      const isSelected = selectedCategories.includes(category);
      categoriesArray.push(new FormControl(isSelected));
    });
  }

  private buildCategoriesFormArray(): FormArray {
    const values = this.categories.map(() => new FormControl(false));
    return this.fb.array(values, [Validators.required]);
  }

  dateValidator(control: FormControl): { [key: string]: any } | null {
    if (!control.value || control.value.trim() === '') {
      return null;
    }

    const dateRegex = /^(\d{2})\/(\d{2})\/(\d{4})$/;
    const match = control.value.match(dateRegex);

    if (!match) {
      return { invalidFormat: true };
    }

    const day = parseInt(match[1], 10);
    const month = parseInt(match[2], 10);
    const year = parseInt(match[3], 10);

    if (month < 1 || month > 12) return { invalidDate: true };
    if (day < 1 || day > 31) return { invalidDate: true };

    const date = new Date(year, month - 1, day);
    if (
      date.getFullYear() !== year ||
      date.getMonth() !== month - 1 ||
      date.getDate() !== day
    ) {
      return { invalidDate: true };
    }

    return null;
  }

  formatDateInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    let value = input.value.replace(/\D/g, '');

    if (value.length > 2) {
      value = value.substring(0, 2) + '/' + value.substring(2);
    }
    if (value.length > 5) {
      value = value.substring(0, 5) + '/' + value.substring(5, 9);
    }

    input.value = value;
    this.profileForm.get('birthDate')?.setValue(value);
  }

  changePhoto(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files?.length) return;

    const file = input.files[0];

    if (file.size > 5 * 1024 * 1024) {
      return;
    }

    this.fileUtils.readAsDataURL(file).then(result => {
      this.imageUser.set(result as string);
      input.value = '';
    });
  }

  removePhoto(): void {
    this.imageUser.set(null);
  }

  submitForm(): void {
    this.submittedForm.set(true);
    this.markFormGroupTouched(this.profileForm);

    let categorisLenght = this.getSelectedCategories().length 
    
    this.loading.set(true);

    const formData: ProfileFormData = {
      email: this.userProfile()?.email || '',
      first_name: this.profileForm.value.firstName?.trim() || '',
      last_name: this.profileForm.value.lastName?.trim() || '',
      data_nasc: this.dateUtils.formatToApiDate(
        typeof this.profileForm.value.birthDate === 'string'
          ? this.profileForm.value.birthDate
          : ''
      ), categories: this.getSelectedCategories(),
      profile_picture: this.imageUser()
    };
    
    this.authService.saveFullProfile(formData).subscribe({
      next: (response) => { 
        this.loading.set(false);
        this.updateLocalProfileData(formData);
        
        this.showSuccessModal();
      },
      error: (err) => {
        this.loading.set(false);
        this.showErrorModal(err?.error?.message);
      }
    });
  }

  private showSuccessModal(): void {
    this.responseModalConfig = {
      title: 'Perfil Salvo!',
      message: 'Seu perfil foi salvo com sucesso. Você será redirecionado em instantes.',
      type: 'success',
      confirmText: 'Continuar',
      showCancel: false
    };
    this.responseModalVisible = true;
  }

  private showErrorModal(message: string): void {
    this.responseModalConfig = {
      title: 'Erro',
      message: message,
      type: 'error',
      confirmText: 'Tentar Novamente',
      showCancel: false
    };
    this.responseModalVisible = true;
  }

  onResponseModalConfirm(): void {
    if (this.responseModalConfig.type === 'success') {
      this.router.navigate(['/app/recs']).then(() => {
        window.location.reload();
      });
    }
    this.closeResponseModal();
  }

  closeResponseModal(): void {
    this.responseModalVisible = false;
  }

  private updateLocalProfileData(formData: ProfileFormData): void {
    this.userProfile.update(profile => {
      if (!profile) return null;

      return {
        ...profile,
        first_name: formData.first_name,
        last_name: formData.last_name,
        data_nasc: formData.data_nasc || undefined,
        categorias: formData.categories,
        profile_picture: formData.profile_picture
      };
    });
  }

  private getSelectedCategories(): string[] {
    const categoriesArray = this.profileForm.get('categories') as FormArray;
    return categoriesArray.controls
      .map((control, index) => control.value ? this.categories[index] : null)
      .filter(Boolean) as string[];
  }

  private markFormGroupTouched(formGroup: FormGroup | FormArray): void {
    Object.values(formGroup.controls).forEach(control => {
      control.markAsTouched();
      if (control instanceof FormGroup || control instanceof FormArray) {
        this.markFormGroupTouched(control);
      }
    });
  }

  syncDatepickerValue(): void {
    setTimeout(() => {
      const input = document.getElementById('data') as HTMLInputElement;
      if (input?.value) {
        const value = input.value.trim();
        this.profileForm.get('birthDate')?.setValue(value);
        this.profileForm.get('birthDate')?.markAsDirty();
        this.profileForm.get('birthDate')?.updateValueAndValidity();

      }
    }, 50);
  }

}